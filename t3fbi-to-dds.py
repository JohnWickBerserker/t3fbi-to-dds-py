import os
import sys
import struct
import io

class FbiHeader(object):
    def __init__(self):
        self.type = 0
        self.width = 0
        self.height = 0
        self.mipmaps = 0
        self.compressed = 0
        self.uncompressed = 0

def read_fbi_header(file):
    header_struct = '<LHHHHBffffHHLL'
    header_raw = file.read(struct.calcsize(header_struct))
    header_raw = struct.unpack(header_struct, header_raw)
    result = FbiHeader()
    result.type = header_raw[1]
    result.width = header_raw[3]
    result.height = header_raw[4]
    result.mipmaps = header_raw[5]
    result.compressed = header_raw[12]
    result.uncompressed = header_raw[13]
    return result

def read_long_number(file):
    b = file.read(1)[0]
    result = b
    while b == 0xFF:
        b = file.read(1)[0]
        result += b
    return result

def decompress(indata, uncompressed_size):
    with io.BytesIO(bytearray(b'\x00') * uncompressed_size) as outstream:
        with io.BytesIO(indata) as instream:
            while True:
                firstbyte = instream.read(1)[0]
                datalen = firstbyte >> 4
                repeat = firstbyte & 0xF
                if datalen == 15:
                    datalen += read_long_number(instream)
                data = instream.read(datalen)
                outstream.write(data)
                backref_raw = instream.read(2)
                if len(backref_raw) == 0:
                    break
                backref = struct.unpack('<H', backref_raw)[0]
                if repeat == 15:
                    repeat += read_long_number(instream)
                repeat += 4
                view = outstream.getbuffer()
                count = repeat
                i = outstream.tell()
                while count > 0:
                    view[i] = view[i-backref]
                    i += 1
                    count -= 1
                view = None
                outstream.seek(repeat, os.SEEK_CUR)
        return outstream.getvalue()

class DdsHeader(object):
    def __init__(self):
        self.height = 0
        self.width = 0
        self.datalen = 0
        self.mipmaps = 0
        self.type = 0

def write_dds_header(file, header):
    if header.mipmaps > 1:
        flags = 0xA1007
        caps = 0x401008
    else:
        flags = 0x81007
        caps = 0x1000
    header_values = [
        0x20534444, 0x7C, flags, header.height, header.width, header.datalen, 1, header.mipmaps, 0x20, 0x4,
        header.type, caps]
    dds_header_struct = '<LLLLLLLL44xLLL20xL16x'
    if header.type == 0x30315844:
        header_values.extend([0x53, 0x03, 0x0, 0x1, 0x3])
        dds_header_struct += 'LLLLL'
    data = struct.pack(dds_header_struct, *header_values)
    file.write(data)

def write_dxt1_data(file, data):
    c0_pos = 0
    c1_pos = len(data) // 4
    index_pos = len(data) // 2
    block_count = len(data) // 8
    for _ in range(block_count):
        file.write(data[c0_pos : c0_pos+2])
        c0_pos += 2
        file.write(data[c1_pos : c1_pos+2])
        c1_pos += 2
        file.write(data[index_pos : index_pos+4])
        index_pos += 4

def write_dxt5_data(file, data):
    a0_pos = 0
    a1_pos = len(data) // 16
    a_index_pos = len(data) // 8
    c0_pos = len(data) // 2
    c1_pos = len(data) // 2 + len(data) // 8
    index_pos = len(data) // 2 + len(data) // 4
    block_count = len(data) // 16
    for _ in range(block_count):
        file.write(data[a0_pos : a0_pos+1])
        a0_pos += 1
        file.write(data[a1_pos : a1_pos+1])
        a1_pos += 1
        file.write(data[a_index_pos : a_index_pos+6])
        a_index_pos += 6
        file.write(data[c0_pos : c0_pos+2])
        c0_pos += 2
        file.write(data[c1_pos : c1_pos+2])
        c1_pos += 2
        file.write(data[index_pos : index_pos+4])
        index_pos += 4

def write_bc5_data(file, data):
    r0_pos = 0
    r1_pos = len(data) // 16
    r_index_pos = len(data) // 8
    g0_pos = len(data) // 2
    g1_pos = len(data) // 2 + len(data) // 16
    g_index_pos = len(data) // 2 + len(data) // 8
    block_count = len(data) // 16
    for _ in range(block_count):
        file.write(data[r0_pos : r0_pos+1])
        r0_pos += 1
        file.write(data[r1_pos : r1_pos+1])
        r1_pos += 1
        file.write(data[r_index_pos : r_index_pos+6])
        r_index_pos += 6
        file.write(data[g0_pos : g0_pos+1])
        g0_pos += 1
        file.write(data[g1_pos : g1_pos+1])
        g1_pos += 1
        file.write(data[g_index_pos : g_index_pos+6])
        g_index_pos += 6

fbi_type_to_dds = {
    1: 0x31545844,
    2: 0x35545844,
    4: 0x30315844
}
default_dds_type = 0x31545844
fbi_bytes_transformer = {
    1: write_dxt1_data,
    2: write_dxt5_data,
    4: write_bc5_data
}
default_transformer = write_dxt1_data

def main(argv):
    if len(argv) < 1:
        print('input filename')
        return
    filename = argv[0]
    output_filename = filename + '.dds'
    with open(filename, 'rb') as file:
        fbi_header = read_fbi_header(file)
        if fbi_header.type not in fbi_type_to_dds:
            print('unsupported fbi type: ' + str(fbi_header.type))
        compressed_data = file.read(fbi_header.compressed)
        decompressed_data = decompress(compressed_data, fbi_header.uncompressed)
        with open(output_filename, 'wb') as output:
            dds_header = DdsHeader()
            dds_header.width = fbi_header.width
            dds_header.height = fbi_header.height
            dds_header.mipmaps = fbi_header.mipmaps
            dds_header.datalen = fbi_header.uncompressed
            if fbi_header.type in fbi_type_to_dds:
                dds_header.type = fbi_type_to_dds[fbi_header.type]
            else:
                dds_header.type = default_dds_type
            write_dds_header(output, dds_header)
            if fbi_header.type in fbi_bytes_transformer:
                fbi_bytes_transformer[fbi_header.type](output, decompressed_data)
            else:
                default_transformer(output, decompressed_data)

if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except Exception as exc:
        sys.stderr.write("%s\n" % exc)
        sys.exit(1)
