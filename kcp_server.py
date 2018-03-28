#!/usr/bin/python
# encoding=utf-8

import socket
import py_kcp
import time
import errno

udp_addr = None

def out_fun(data,user_data):
	user_data.sendto(data,udp_addr)

def recv_udp(sock):
	global udp_addr
	try:
		data,udp_addr = sock.recvfrom(65535)
		return data
	except socket.error,arg:
		eno,msg = arg
		if eno != errno.EAGAIN and eno != errno.EINTR: 
			sock.close()
	return None

udp_sock   = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
server_kcp = py_kcp.py_kcp(1,udp_sock,out_fun,None)

if __name__ == '__main__':
	udp_sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
	udp_sock.setblocking(0)
	udp_sock.bind(("127.0.0.1",8000))
	while True:
		server_kcp.update(time.time())
		data = server_kcp.recv_data()
		if data != None:
			print("recv=%s"%(data))
			server_kcp.send_data(data)
		data = recv_udp(udp_sock)
		if data != None:
			server_kcp.input_data(data)
		time.sleep(0.01)
