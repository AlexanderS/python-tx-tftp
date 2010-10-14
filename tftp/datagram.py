'''
@author: shylent
'''
from tftp.errors import (WireProtocolError, InvalidOpcodeError, 
    PayloadDecodeError, InvalidErrorcodeError)
import struct

OP_RRQ = 1
OP_WRQ = 2
OP_DATA = 3
OP_ACK = 4
OP_ERROR = 5

ERR_NOT_DEFINED = 0
ERR_FILE_NOT_FOUND = 1
ERR_ACCESS_VIOLATION = 2
ERR_DISK_FULL = 3
ERR_ILLEGAL_OP = 4
ERR_TID_UNKNOWN = 5
ERR_FILE_EXISTS = 6
ERR_NO_SUCH_USER = 7

errors = {
    ERR_NOT_DEFINED :       "",
    ERR_FILE_NOT_FOUND  :   "File not found",
    ERR_ACCESS_VIOLATION :  "Access violation",
    ERR_DISK_FULL :         "Disk full or allocation exceeded",
    ERR_ILLEGAL_OP :        "Illegal TFTP operation",
    ERR_TID_UNKNOWN :       "Unknown transfer ID",
    ERR_FILE_EXISTS :       "File already exists",
    ERR_NO_SUCH_USER :      "No such user"

}

def split_opcode(datagram):
    """Split the raw datagram into opcode and payload.

    @param datagram: raw datagram
    @type datagram: C{str}

    @return: a 2-tuple, the first item is the opcode and the second item is the payload
    @rtype: (C{int}, C{str})

    @raise WireProtocolError: if the opcode cannot be extracted

    """

    try:
        return struct.unpack("!H", datagram[:2])[0], datagram[2:]
    except struct.error:
        raise WireProtocolError("Failed to extract the opcode")


class TFTPDatagram(object):
    """Base class for datagrams

    @cvar opcode: The opcode, corresponding to this datagram
    @type opcode: C{int}

    """

    opcode = None
    
    @classmethod
    def from_wire(cls, payload):
        """Parse the payload and return a datagram object

        @param payload: Binary representation of the payload (without the opcode)
        @type payload: C{str}

        """
        raise NotImplementedError("Subclasses must override this")

    def to_wire(self):
        """Return the wire representation of the datagram.

        @rtype: C{str}

        """
        raise NotImplementedError("Subclasses must override this")


class RQDatagram(TFTPDatagram):
    """Base class for "RQ" (request) datagrams.

    @ivar filename: File name, that corresponds to this request.
    @type filename: C{str}

    @ivar mode: Transfer mode. Valid values are C{netascii} and C{octet}.
    Case-insensitive.
    @type mode: C{str}

    """
    
    @classmethod
    def from_wire(cls, payload):
        """Parse the payload and return a RRQ/WRQ datagram object.

        @return: datagram object
        @rtype: L{RRQDatagram} or L{WRQDatagram}

        @raise PayloadDecodeError: if there were not enough fields in the payload.
        Fields are terminated by NUL.

        """
        parts = payload.split('\x00')
        try:
            return cls(parts[0], parts[1])
        except IndexError:
            raise PayloadDecodeError("Not enough fields in the payload")

    def __init__(self, filename, mode):
        self.filename = filename
        self.mode = mode.lower()
        
    def __repr__(self):
        return "<%s(filename=%s, mode=%s)>" % (self.__class__.__name__,
                                               self.filename, self.mode)
    
    def to_wire(self):
        return ''.join((struct.pack("!H", self.opcode),
                        self.filename, '\x00', self.mode, '\x00'))

class RRQDatagram(RQDatagram):
    opcode = OP_RRQ

class WRQDatagram(RQDatagram):
    opcode = OP_WRQ

class DATADatagram(TFTPDatagram):
    """A DATA datagram

    @ivar blocknum: A block number, that this chunk of data is associated with
    @type blocknum: C{int}

    @ivar data: binary data
    @type data: C{str}

    """
    opcode = OP_DATA
    
    @classmethod
    def from_wire(cls, payload):
        """Parse the payload and return a L{DATADatagram} object.

        @param payload: Binary representation of the payload (without the opcode)
        @type payload: C{str}

        @return: A L{DATADatagram} object
        @rtype: L{DATADatagram}

        @raise PayloadDecodeError: if the format of payload is incorrect

        """
        try:
            blocknum, data = struct.unpack('!H', payload[:2])[0], payload[2:]
        except struct.error:
            raise PayloadDecodeError()
        return cls(blocknum, data)

    def __init__(self, blocknum, data):
        self.blocknum = blocknum
        self.data = data
    
    def __repr__(self):
        return "<%s(blocknum=%s, %s bytes of data)>" % (self.__class__.__name__,
                                                        self.blocknum, len(self.data))
        
    def to_wire(self):
        return ''.join((struct.pack('!HH', self.opcode, self.blocknum), self.data))

class ACKDatagram(TFTPDatagram):
    """An ACK datagram.

    @ivar blocknum: Block number of the data chunk, which this datagram is supposed to acknowledge
    @type blocknum: C{int}

    """
    opcode = OP_ACK
    
    @classmethod
    def from_wire(cls, payload):
        """Parse the payload and return a L{ACKDatagram} object.

        @param payload: Binary representation of the payload (without the opcode)
        @type payload: C{str}

        @return: An L{ACKDatagram} object
        @rtype: L{ACKDatagram}

        @raise PayloadDecodeError: if the format of payload is incorrect

        """
        try:
            blocknum = struct.unpack('!H', payload)[0]
        except struct.error:
            raise PayloadDecodeError("Unable to extract the block number")
        return cls(blocknum)
    
    def __init__(self, blocknum):
        self.blocknum = blocknum
    
    def __repr__(self):
        return "<%s(blocknum=%s)>" % (self.__class__.__name__, self.blocknum)
    
    def to_wire(self):
        return struct.pack('!HH', self.opcode, self.blocknum)

class ERRORDatagram(TFTPDatagram):
    """An ERROR datagram.

    @ivar errorcode: A valid TFTP error code
    @type errorcode: C{int}

    @ivar errmsg: An error message, describing the error condition in which this
    datagram was produced
    @type errmsg: C{str}

    """
    opcode = OP_ERROR
    
    @classmethod
    def from_wire(cls, payload):
        """Parse the payload and return a L{ERRORDatagram} object.

        This method violates the standard a bit - if the error string was not
        extracted, a default error string is generated, based on the error code.

        @param payload: Binary representation of the payload (without the opcode)
        @type payload: C{str}

        @return: An L{ERRORDatagram} object
        @rtype: L{ERRORDatagram}

        @raise PayloadDecodeError: if the format of payload is incorrect
        @raise InvalidErrorcodeError: a more specific exception, that is raised
        if the error code was successfully, extracted, but it does not correspond
        to any known/standartized error code values.

        """
        try:
            errorcode = struct.unpack('!H', payload[:2])[0]
        except struct.error:
            raise PayloadDecodeError("Unable to extract the error code")
        if not errorcode in errors:
            raise InvalidErrorcodeError(errorcode)
        errmsg = payload[2:].split('\x00')[0]
        if not errmsg:
            errmsg = errors[errorcode]
        return cls(errorcode, errmsg)
    
    @classmethod
    def from_code(cls, errorcode, errmsg=None):
        """Create an L{ERRORDatagram}, given an error code and, optionally, an
        error message to go with it. If not provided, default error message for
        the given error code is used.

        @param errorcode: An error code (one of L{errors})
        @type errorcode: C{int}

        @param errmsg: An error message (optional)
        @type errmsg: C{str} or C{NoneType}

        @raise InvalidErrorcodeError: if the error code is not known

        @return: an L{ERRORDatagram}
        @rtype: L{ERRORDatagram}

        """
        if not errorcode in errors:
            raise InvalidErrorcodeError(errorcode)
        if errmsg is None:
            errmsg = errors[errorcode]
        return cls(errorcode, errmsg)
        
        
    def __init__(self, errorcode, errmsg):
        self.errorcode = errorcode
        self.errmsg = errmsg
        
    def to_wire(self):
        return ''.join((struct.pack('!HH', self.opcode, self.errorcode),
                        self.errmsg, '\x00'))

class _TFTPDatagramFactory(object):
    """Encapsulates the creation of datagrams based on the opcode"""
    _dgram_classes = {
        OP_RRQ: RRQDatagram,
        OP_WRQ : WRQDatagram,
        OP_DATA : DATADatagram,
        OP_ACK : ACKDatagram,
        OP_ERROR : ERRORDatagram
    }

    def __call__(self, opcode, payload):
        """Create a datagram, given an opcode and payload.

        Errors, that occur during datagram creation are propagated as-is.

        @param opcode: opcode
        @type opcode: C{int}

        @param payload: payload
        @type payload: C{str}

        @return: datagram object
        @rtype: L{TFTPDatagram}

        @raise InvalidOpcodeError: if the opcode is not recognized

        """
        try:
            datagram_class = self._dgram_classes[opcode]
        except KeyError:
            raise InvalidOpcodeError(opcode) 
        return datagram_class.from_wire(payload)

TFTPDatagramFactory = _TFTPDatagramFactory()
