import sys
import serial

# CMDs
CRLF = '\r\n'
SYNC = f"?{CRLF}"
SYNC_ACK = f"Synchronized{CRLF}"
CRYS_FREQ = f"12000{CRLF}"
ECHO_OFF = f"A 0{CRLF}"
PART_NUM = f"J{CRLF}"
PREP_FLASH = f"P 0 15{CRLF}"
ERASE_FLASH = f"E 0 15{CRLF}"
UNLOCK = f"U 23130{CRLF}"
WRITE_RAM = f"W 268436480 512{CRLF}"  # 512 bytes at 0x10000400
COPY = lambda a: f"C {a} 268436480 512{CRLF}"
READ_FLASH = lambda a: f"R {a} 512{CRLF}"
GO = f"G 0 T{CRLF}"

# Res
CMD_SUCCESS = f"0{CRLF}"
OK = f"OK{CRLF}"

# Const
MCU_CHECKSUM_VEC = 7
WORD = 4


def new_cmd(ser, cmd_str, exp_res_str=CMD_SUCCESS):
    cmd_b = bytes(cmd_str, 'ascii')
    exp_res_b = bytes(exp_res_str, 'ascii')
    ser.write(cmd_b)
    ser.flush()
    res = ser.read(len(exp_res_b))
    return res == exp_res_b


def split_bin(file=sys.argv[1], split_len=512):
    f_bin = open(file, 'rb')
    bin = f_bin.read()
    f_bin.close()
    bin_split = [bin[i:i+split_len] for i in range(0, len(bin), split_len)]
    if len(bin_split[-1]) < split_len:
        zeros = [0 for _ in range(split_len - len(bin_split[-1]))]
        bin_split[-1] += bytes(zeros)
    return bin_split


def fix_user_code_checksum(bin):
    user_code = 0
    for i in range(7):
        user_code += int.from_bytes(bin[i*WORD:(i*WORD)+WORD], 'little')
    user_code = -user_code
    print(f"user code: {str(user_code)}")
    return (bin[:MCU_CHECKSUM_VEC * WORD]
            + user_code.to_bytes(WORD, byteorder='little', signed=True)
            + bin[(MCU_CHECKSUM_VEC + 1) * WORD:])


def init_serial(p='/dev/ttyUSB0', b=115200, t=1):
    return serial.Serial(port=p,
                         baudrate=b,
                         bytesize=serial.EIGHTBITS,
                         parity=serial.PARITY_NONE,
                         stopbits=serial.STOPBITS_ONE,
                         timeout=t)


def synchronize(ser):
    try:
        assert new_cmd(ser, SYNC, SYNC_ACK) is True
        assert new_cmd(ser, SYNC_ACK, f"{SYNC_ACK}{OK}") is True
        assert new_cmd(ser, CRYS_FREQ, f"{CRYS_FREQ}{OK}") is True
        assert new_cmd(ser, ECHO_OFF, f"{ECHO_OFF}{CMD_SUCCESS}") is True
    except:
        print("sync fail")
        exit(-1)


def init_flash(ser):
    try:
        assert new_cmd(ser, UNLOCK) is True
        assert new_cmd(ser, PREP_FLASH) is True
        assert new_cmd(ser, ERASE_FLASH) is True
        assert new_cmd(ser, UNLOCK) is True
    except:
        print("init flash fail")
        exit(-1)


def flash_bin(ser, addr, bin):
    try:
        print(f"flash #{addr}...")
        assert new_cmd(ser, PREP_FLASH) is True
        assert new_cmd(ser, WRITE_RAM) is True
        ser.write(bin)
        ser.flush()
        assert new_cmd(ser, PREP_FLASH) is True
        assert new_cmd(ser, COPY(addr)) is True
    except:
        print("flash fail")
        exit(-1)


def verify_bin(ser, addr, exp_bin):
    try:
        assert new_cmd(ser, READ_FLASH(addr)) is True
        bin = ser.read(512)
        if bin == exp_bin:
            print(f"verify #{addr}: OK")
        else:
            print(f"verify #{addr}: fail")
    except:
        print("verify fail")
        exit(-1)


def go(ser):
    if not new_cmd(ser, GO):
        print("go fail")
        exit(-1)


if __name__ == '__main__':
    ser = init_serial()
    synchronize(ser)
    print("sync: OK")
    init_flash(ser)
    print("init flash: OK")
    
    # bin stuff (1/2)
    bin_list = split_bin()
    bin_list[0] = fix_user_code_checksum(bin_list[0])
    bin_list.reverse()
    flash_addr = [x*512 for x in range(len(bin_list))]
    flash_addr.reverse()

    # flash (top -> bottom)
    for idx in range(len(bin_list)):
        flash_bin(ser, flash_addr[idx], bin_list[idx])

    # bin stuff (2/2)
    bin_list.reverse()
    flash_addr.reverse()

    # verify (bottom -> top)
    for idx in range(len(bin_list)):
        verify_bin(ser, flash_addr[idx], bin_list[idx])

    # go
    go(ser)
    print("goto 0x00000000")
