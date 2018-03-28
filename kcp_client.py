#!/usr/bin/python
# encoding=utf-8

import py_kcp
import time
import socket
import sys
import random
import thread
import threading
import errno

#生成聊天数据
letter_list  = []
start_leter  = 97   #a 的 ascii
letter_count = 26   #字母总个数

#初始化26个字母
def make_letter():
	for i in range(0,letter_count):
		letter_list.append(chr(start_leter+i))

def make_chat(word_down,word_up,letter_down,letter_up):
	word_count = random.randint(word_down,word_up)
	result = []
	for i in range(0,word_count):
		data = []
		word_count = random.randint(letter_down,letter_up)
		for j in range(0,word_count):
			index = random.randint(0,letter_count - 1)
			data.append(letter_list[index])
		result.append("".join(data))

	return " ".join(result)

class data_thread(threading.Thread):
	def __init__(self):
		threading.Thread.__init__(self)
		self.m_lock       = thread.allocate_lock()
		self.m_quit       = False
		self.m_interval   = 0.5 
		self.m_last 	  = 0
		self.m_data_queue = []
		self.m_head 	  = 0
		self.m_tail 	  = 0
		self.m_cap 		  = 100
		for i in xrange(self.m_cap):
			self.m_data_queue.append(0)

	def get_data(self):
		self.m_lock.acquire()	
		#-1 表示该队列已满，相等表示该队列为空
		if self.m_head == self.m_tail or self.m_tail == -1:
			data = None
		else:
			data = self.m_data_queue[self.m_head] 
			self.m_head += 1
			self.m_head %= self.m_cap 
		self.m_lock.release()
		return data

	def add_data(self,data):
		self.m_lock.acquire()
		#self.m_tail 表示可用的槽位
		self.m_data_queue[self.m_tail] = data
		self.m_tail += 1 
		self.m_tail %= self.m_cap
		if self.m_tail == self.m_head:
			self.m_head += 1
			self.m_head %= self.m_cap
		self.m_lock.release()

	def std_data(self):
		data = sys.stdin.readline()
		data = data[0:len(data) - 1]

	def run(self):
		while True:
			time.sleep(0.01)
			cur_tm = time.time() * 1000
			if cur_tm < self.m_last:
				continue
			count = random.randint(1,10)
			self.m_last = cur_tm + random.randint(200,500) 
			for i in xrange(count):
				data = make_chat(3,20,3,10)
				if data == 'quit': 
					self.m_quit = True
					break
				if data != '' and data != None:
					self.add_data(data)

def out_fun(data,user_data):
	user_data.sendto(data,("127.0.0.1",8000))
	
def recv_udp(sock):
	try:
		data,udp_addr = sock.recvfrom(65535)
		return data
	except socket.error,arg:
		eno,msg = arg
		if eno != errno.EAGAIN and eno != errno.EINTR: 
			sock.close()
	return None 

udp_sock   = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
client_kcp = py_kcp.py_kcp(1,udp_sock,out_fun,None)
g_thread   = data_thread()

if __name__ == '__main__':
	make_letter()
	udp_sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
	udp_sock.setblocking(0)
	g_thread.start()
	client_kcp.set_nodelay(0,40,0,0)
	while not g_thread.m_quit:
		count = 0
		while count <= 10: 
			data = g_thread.get_data()
			if data != None:
				print("%3d send=%s"%(len(data),data))
				client_kcp.send_data(data)
			else:
				break
			count += 1
		data = client_kcp.recv_data()
		if data != None:
			print("%3d recv=%s"%(len(data),data))
		client_kcp.update(time.time())
		data = recv_udp(udp_sock)
		if data != None:
			client_kcp.input_data(data)
		time.sleep(0.01)