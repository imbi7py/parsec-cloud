import zmq
from os import environ


CONFIG = {
    'ZMQ_CONTEXT_FACTORY': zmq.Context.instance,
    'SERVER_PUBLIC': '',
    'SERVER_SECRET': '',
    'TEST_CONTROL_PIPE': '',
    'DB_URL': environ.get('DB_URL', '<inmemory>'),
    'BLOCKSTORE_URL': environ.get('BLOCKSTORE_URL', '<inbackend>'),
    'ANONYMOUS_PUBKEY': 'y4scJ4mV09t5FJXtjwTctrpFg+xctuCyh+e4EoyuDFA=',
    'ANONYMOUS_PRIVKEY': 'ua1CbOtQ0dUrWG0+Satf2SeFpQsyYugJTcEB4DNIu/c=',
    'CMDS_SOCKET_URL': '',
}
