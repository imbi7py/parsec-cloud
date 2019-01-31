from triopg import UniqueViolationError
from uuid import UUID
from typing import List, Tuple

from parsec.types import DeviceID, OrganizationID
from parsec.backend.beacon import BaseBeaconComponent
from parsec.backend.vlob import (
    BaseVlobComponent,
    VlobError,
    VlobAccessError,
    VlobVersionError,
    VlobNotFoundError,
    VlobAlreadyExistsError,
)
from parsec.backend.drivers.postgresql.handler import PGHandler


class PGVlobComponent(BaseVlobComponent):
    def __init__(self, dbh: PGHandler, beacon_component: BaseBeaconComponent):
        self.dbh = dbh
        self.beacon_component = beacon_component

    async def group_check(
        self, organization_id: OrganizationID, to_check: List[dict]
    ) -> List[dict]:
        changed = []
        to_check_dict = {}
        for x in to_check:
            if x["version"] == 0:
                changed.append({"id": x["id"], "version": 0})
            else:
                to_check_dict[x["id"]] = x

        async with self.dbh.pool.acquire() as conn:
            rows = await conn.fetch(
                """
SELECT DISTINCT ON (vlob_id) vlob_id, version
FROM vlobs
WHERE
    organization = (
        SELECT _id from organizations WHERE organization_id = $1
    )
    AND vlob_id = any($2::uuid[])
ORDER BY vlob_id, version DESC
""",
                organization_id,
                to_check_dict.keys(),
            )

        for id, version in rows:
            # TODO: check acces rights here
            if version != to_check_dict[id]["version"]:
                changed.append({"id": id, "version": version})

        return changed

    async def create(
        self,
        organization_id: OrganizationID,
        id: UUID,
        blob: bytes,
        author: DeviceID,
        notify_beacon: UUID = None,
    ) -> None:
        async with self.dbh.pool.acquire() as conn:
            async with conn.transaction():
                try:
                    result = await conn.execute(
                        """
INSERT INTO vlobs (
    organization, vlob_id, version, blob, author
)
SELECT
    _id,
    $2,
    1,
    $5,
    (
        SELECT _id
        FROM devices
        WHERE
            device_id = $6
            AND organization = organizations._id
    )
FROM organizations
WHERE organization_id = $1
""",
                        organization_id,
                        id,
                        blob,
                        author,
                    )
                except UniqueViolationError:
                    raise VlobAlreadyExistsError()

                if result != "INSERT 0 1":
                    raise VlobError(f"Insertion error: {result}")

                if notify_beacon:
                    await self.beacon_component.ll_update(
                        conn, organization_id, notify_beacon, id, 1, author
                    )

    async def read(
        self, organization_id: OrganizationID, id: UUID, version: int = None
    ) -> Tuple[int, bytes]:
        async with self.dbh.pool.acquire() as conn:
            async with conn.transaction():
                if version is None:
                    data = await conn.fetchrow(
                        """
SELECT version, blob
FROM vlobs
WHERE
    organization = (
        SELECT _id from organizations WHERE organization_id = $1
    )
    AND vlob_id = $2
ORDER BY version DESC LIMIT 1
""",
                        organization_id,
                        id,
                    )
                    if not data:
                        raise VlobNotFoundError()

                else:
                    data = await conn.fetchrow(
                        """
SELECT version, blob
FROM vlobs
WHERE
    organization = (
        SELECT _id from organizations WHERE organization_id = $1
    )
    AND vlob_id = $2
    AND version = $3
""",
                        organization_id,
                        id,
                        version,
                    )
                    if not data:
                        # TODO: not cool to need 2nd request to know the error...
                        exists = await conn.fetchrow(
                            """
SELECT true
FROM vlobs
WHERE
    organization = (
        SELECT _id from organizations WHERE organization_id = $1
    )
    AND vlob_id = $2
""",
                            organization_id,
                            id,
                        )
                        if exists:
                            raise VlobVersionError()

                        else:
                            raise VlobNotFoundError()

            # TODO: check access rights here

        return data[1:]

    async def update(
        self,
        organization_id: OrganizationID,
        id: UUID,
        version: int,
        blob: bytes,
        author: DeviceID,
        notify_beacon: UUID = None,
    ) -> None:
        async with self.dbh.pool.acquire() as conn:
            async with conn.transaction():
                previous = await conn.fetchrow(
                    """
SELECT version
FROM vlobs
WHERE
    organization = (
        SELECT _id from organizations WHERE organization_id = $1
    )
    AND vlob_id = $2
ORDER BY version DESC LIMIT 1
""",
                    organization_id,
                    id,
                )
                # TODO: check access rights here
                if not previous:
                    raise VlobNotFoundError()
                elif previous[0] != version - 1:
                    raise VlobVersionError()

                try:
                    result = await conn.execute(
                        """
INSERT INTO vlobs (
    organization, vlob_id, version, blob, author
)
SELECT
    _id,
    $2, $5, $6,
    (
        SELECT _id
        FROM devices
        WHERE
            device_id = $7
            AND organization = organizations._id
    )
FROM organizations
WHERE organization_id = $1
""",
                        organization_id,
                        id,
                        version,
                        blob,
                        author,
                    )
                except UniqueViolationError:
                    # Should not occurs in theory given we are in a transaction
                    raise VlobVersionError()

                if result != "INSERT 0 1":
                    raise VlobError(f"Insertion error: {result}")

                if notify_beacon:
                    await self.beacon_component.ll_update(
                        conn, organization_id, notify_beacon, id, version, author
                    )
