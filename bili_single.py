# -*- coding: utf-8 -*-

#from gevent import monkey
#monkey.patch_all()
import socket
import json
from random import random
from binascii import hexlify as hh
import time
from pprint import pprint
import gevent

#import urllib
#from bs4 import BeautifulSoup
#
#channel_id = 47202
#response = urllib.request.urlopen("http://live.bilibili.com/api/player?id=cid:" + str(channel_id))
#tree = BeautifulSoup('<root>'+response.read().decode('utf-8')+'</root>', 'lxml')

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
    (120831, 1), (262141, 2), (1114109, 1),
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
    return count

##################################################################
# Actual danmaku part
"""
NORMAL          :   If True, act as danmaku hime
COUNTING_TOTAL  :   If True, count total command number
TOTAL_COUNT_TIME:   Number of seconds to run
total           :   (number of commands, total size of commands)
"""
NORMAL = False
COUNTING_TOTAL = True
TOTAL_COUNT_TIME = 15
HEARTBEAT_CONTENT = b'00000010001000010000000200000001'
total = (0, 0)
send_data_template = [b'',
                      b'001000010000000700000001',
                      b'']


def pack_data(body):
    """Pack the initial connecting data
    
    roomid(int)
    """
    send_data_template[0] = (len(body)+16).to_bytes(4, byteorder="big")
    send_data_template[2] = body
    return b''.join(send_data_template)


def recv(sock, roomid):
    """Receiving and basic parsing of data"""

    # Package length
    re_data = sock.recv(16)
    print(re_data)
    if not re_data:
        print("No incoming data")
        return (0, "")
    length = int(hh(re_data[:4]), 16)
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
            else:
                if command["cmd"] == "DANMU_MSG":
                    msg = command["info"][1]
                elif command["cmd"] == "SEND_GIFT":
                    pre = ""
                    if command["data"].get("num"):
                        pre =  "".join([command["data"]["num"], "X"])
                    msg = "".join([pre,
                                   command["data"]["giftName"],
                                   " from ",
                                   command["data"]["uname"]])
                else:
                    msg = command["cmd"]
                return (length - 16, msg)
    return (0, "")


def start(roomid, loop, roomname, start_count_time=0):
    global total
    
    userid = int(random()*2e14 + 1e14)
    dum = json.dumps({"roomid":roomid, "uid":userid}, separators=(',',':'))
    j = dum.encode('utf-8')

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(("livecmt-2.bilibili.com", 788))

    sock.sendall(pack_data(j))
    recv(sock, roomid)
    print("Connected to room", roomid)

    # Global counting start time
    if start_count_time:
        start_count = start_count_time
    else:
        start_count = time.time()

    heartbeat_timer = time.time()
    try:
        while loop:
            # Heartbeat
            if time.time() - heartbeat_timer > 10:
                print("Sending heartbeat")
                sock.sendall(HEARTBEAT_CONTENT)
                heartbeat_timer = time.time()
            print("Looping")
            size_incre, msg = recv(sock, roomid)
            print("Received:", size_incre)
            gevent.sleep(1)
            
            # Counting process
            if size_incre:
                total = (total[0] + 1,
                         total[1] + size_incre)
                print("count {:>6d}|size {:>10s}|from {:<{}s}|{:<30s}".format(total[0],
                                                                              humansize(total[1]),
                                                                              roomname[:10],
                                                                              20 - str_width(roomname[:10]),
                                                                              msg))
            if (time.time() - start_count >= TOTAL_COUNT_TIME):
                break
    except Exception as e:
        sock.close()
        print(repr(e))
        raise Exception("Error: Closing socket")

    sock.close()

    # Only normal stop reaches here, so it doesn't need to check NORMAL or 
    # COUNTING_TOTAL
    print("End")


def start_with_redo(roomid, loop, roomname, start_count_time):
    while time.time() - start_count_time < TOTAL_COUNT_TIME:
        start(roomid, loop, roomname, start_count_time)
#        try:
#            start(roomid, loop, roomname, start_count_time)
#        except:
#            print("Reconnecting to ", roomid)
##            gevent.sleep(5)
#            continue
        
if __name__ == "__main__":
    start_with_redo(33616, 1, "No-Name", time.time())