# -*- coding: utf-8 -*-

from gevent import monkey
monkey.patch_all()
import socket
import json
from random import random
from binascii import hexlify as hh
import time
from pprint import pprint
import gevent
import gevent.event
from sys import argv


suffixes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
def humansize(nbytes):
    if nbytes == 0: return '0 B'
    i = 0
    while nbytes >= 1024 and i < len(suffixes)-1:
        nbytes /= 1024.
        i += 1
    f = ('%.2f' % nbytes).rstrip('0').rstrip('.')
    return '%s %s' % (f, suffixes[i])

widths = [
    (126,    1), (159,    0), (687,     1), (710,   0), (711,   1),
    (727,    0), (733,    1), (879,     0), (1154,  1), (1161,  0),
    (4347,   1), (4447,   2), (7467,    1), (7521,  0), (8369,  1),
    (8426,   0), (9000,   1), (9002,    2), (11021, 1), (12350, 2),
    (12351,  1), (12438,  2), (12442,   0), (19893, 2), (19967, 1),
    (55203,  2), (63743,  1), (64106,   2), (65039, 1), (65059, 0),
    (65131,  2), (65279,  1), (65376,   2), (65500, 1), (65510, 2),
    (120831, 1), (262141, 2), (1114109, 1)
]

def str_width(string):
    count = 0
    for char in string:
        temp = ord(char)
        if temp  == 0xe or temp  == 0xf:
            pass
        elif temp  > widths[-1][0]:
            count += 1
        else:
            for num, wid in widths:
                if temp  <= num:
                    count += wid
                    break
    return count

##################################################################
# Actual danmaku part
"""
NORMAL          :   If True, act as danmaku hime
COUNTING_TOTAL  :   If True, count total command number
TOTAL_COUNT_TIME:   Number of seconds to run
total           :   (number of commands, total size of commands)
"""
# 1 to also print connect and reconnect
PRINT_LV = 0
NORMAL = False
COUNTING_TOTAL = True
HEARTBEAT_CONTENT = b'00000010001000010000000200000001'
total = (0, 0)
send_data_template = [b'',
                     (16).to_bytes(2, byteorder="big"),
                     (1).to_bytes(2, byteorder="big"),
                     (7).to_bytes(4, byteorder="big"),
                     (1).to_bytes(4, byteorder="big"),
                     b'']


def pack_data(body):
    """Pack the initial connecting data

    roomid(int)
    """
    send_data_template[0] = (len(body)+16).to_bytes(4, byteorder="big")
    send_data_template[5] = body
    return b''.join(send_data_template)


def recv(sock, roomid):
    """Receiving and basic parsing of data"""

    # Package length
    re_data = sock.recv(16)
    if re_data:
        length = int(hh(re_data[:4]), 16)
    elif re_data == b'':
        raise Exception("Received empty string")
    if NORMAL:
        print("length", length)

    # Valid
    if length > 16:
        typeid = int(hh(re_data[8:12]), 16)
        re_data = sock.recv(length-16)
        if typeid < 4:  # Audience count
            if NORMAL:
                print(roomid, "count", int(hh(re_data), 16))
        else:
            command = json.loads(re_data.decode('utf-8'))
            if NORMAL:
                pprint(command)
            elif COUNTING_TOTAL:
                if command["cmd"] == "DANMU_MSG":
                    msg = command["info"][1]
                elif command["cmd"] == "SEND_GIFT":
                    pre = ""
                    if command["data"].get("num"):
                        pre =  "".join([str(command["data"]["num"]), "X"])
                    msg = "".join([pre,
                                   command["data"]["giftName"],
                                   " from ",
                                   command["data"]["uname"]])
                else:
                    msg = command["cmd"]
                return (length - 16, msg)
    return (0, "")


def start(roomid, roomname_async, end_time, current_rooms_async):
    global total

    userid = int(random()*2e14 + 1e14)
    dum = json.dumps({"roomid":roomid, "uid":userid}, separators=(',',':'))
    init_data = pack_data(dum.encode('utf-8'))

    while (time.time() < end_time):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            sock.setsockopt(socket.SOL_TCP, socket.TCP_KEEPIDLE, 60)
            sock.setsockopt(socket.SOL_TCP, socket.TCP_KEEPCNT, 4)
            sock.setsockopt(socket.SOL_TCP, socket.TCP_KEEPINTVL, 15)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.connect(("livecmt-2.bilibili.com", 788))
            sock.sendall(init_data)
            if PRINT_LV:
                print("Connected to room", roomid)
            heartbeat_timer = time.time()
            while True:
                if time.time() - heartbeat_timer > 10:
                    sock.sendall(HEARTBEAT_CONTENT)
                    heartbeat_timer = time.time()
                size_incre, msg = recv(sock, roomid)
                if size_incre:
                    total = (total[0] + 1,
                             total[1] + size_incre)
                    current_roomname = roomname_async.get()
                    print("count {:>6d}|size {:>10s}|from {:<{}s}|{:<30s}".format(total[0],
                                                                                  humansize(total[1]),
                                                                                  current_roomname[:10],
                                                                                  20 + len(current_roomname[:10]) - str_width(current_roomname[:10]),
                                                                                  msg))
                if (time.time() > end_time):
                    sock.close()
                    break
                if roomid not in current_rooms_async.get():
                    if PRINT_LV:print("Not in current_rooms_async")
                    raise gevent.GreenletExit
                gevent.sleep(0)
        except OSError as e:
            if PRINT_LV:
                print("Socket error {} {}".format(sock.getsockname(), repr(e)))
            sock.close()
            continue
        # Force redo
        except KeyboardInterrupt:
            sock.close()
            raise KeyboardInterrupt
        except gevent.GreenletExit:
            if PRINT_LV:
                print("Got terminate signal")
            sock.close()
            break
        except Exception as e:
            if PRINT_LV:
                print(repr(e))
            sock.close()
            continue

    # Avoid too many messages
    if NORMAL:
        print("End")

# Just some simple test
if __name__ == "__main__":
    room = int(argv[1])
    current_rooms_async = gevent.event.AsyncResult()
    current_rooms_async.set([room])
    start(current_rooms_async.get()[0], "No Name",time.time() + 120, current_rooms_async)
