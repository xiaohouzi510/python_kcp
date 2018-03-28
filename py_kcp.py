#!/usr/bin/python
# encoding=utf-8

import struct

IKCP_RTO_NDL 	 = 30			#no delay min rto
IKCP_RTO_MIN 	 = 100			#normal min rto
IKCP_RTO_DEF 	 = 200
IKCP_RTO_MAX 	 = 60000
IKCP_CMD_PUSH 	 = 81			#cmd: push data
IKCP_CMD_ACK  	 = 82			#cmd: ack
IKCP_CMD_WASK 	 = 83			#cmd: window probe (ask)
IKCP_CMD_WINS 	 = 84			#cmd: window size (tell)
IKCP_ASK_SEND 	 = 1			#need to send IKCP_CMD_WASK
IKCP_ASK_TELL    = 2		    # need to send IKCP_CMD_WINS
IKCP_WND_SND     = 32
IKCP_WND_RCV 	 = 32
IKCP_MTU_DEF 	 = 1400
IKCP_ACK_FAST	 = 3
IKCP_INTERVAL	 = 100
IKCP_OVERHEAD    = 24
IKCP_DEADLINK    = 20
IKCP_THRESH_INIT = 2
IKCP_THRESH_MIN  = 2
IKCP_PROBE_INIT  = 7000			# 7 secs to probe window size
IKCP_PROBE_LIMIT = 120000		# up to 120 secs to probe window

TYPE_32_LEN = 4
TYPE_16_LEN = 2
TYPE_8_LEN  = 1

#报文段结点
class segment_node():
	def __init__(self):
		self.m_next 		  = None
		self.m_front  		  = None
		self.m_user_key       = 0
		self.m_cmd            = 0
		self.m_index          = 0
		self.m_wind_size      = 0
		self.m_time_stamp     = 0
		self.m_sequence    	  = 0
		self.m_receive_next   = 0
		self.m_resend_tm      = 0
		self.m_rto 			  = 0
		self.m_fast_ack       = 0
		self.m_time_out 	  = 0
		self.m_data 		  = ''

	def log(self):
		pattern_str = "index=%d win_size=%d tm=%d seq=%d rc_next=%d re_tm=%d rto=%d data=%s"
		return pattern_str%(self.m_index,self.m_wind_size,self.m_time_stamp,self.m_sequence,self.m_receive_next,self.m_resend_tm,self.m_rto,self.m_data)

#报文链表
class segment_link(): 
	def __init__(self):
		self.m_head   = None  
		self.m_tail   = None
		self.m_count  = 0

#ack 数据
class ack_data(): 
	def __init__(self):
		self.m_time_stamp = 0
		self.m_sequence   = 0

#kcp
class py_kcp():
	def __init__(self,user_key,user_data,out_put_fun,write_log_fun):
		self.m_user_key 		 = user_key
		self.m_user_data 		 = user_data
		self.m_mtu 				 = IKCP_MTU_DEF 
		self.m_mss 				 = self.m_mtu - IKCP_OVERHEAD
		self.m_ack_knowledge 	 = 0
		self.m_send_next 		 = 0
		self.m_receive_next      = 0
		self.m_ssthresh 		 = IKCP_THRESH_INIT
		self.m_rtt_avg 			 = 0
		self.m_rtt_diff 		 = 0
		self.m_rto 				 = IKCP_RTO_DEF
		self.m_min_rto 			 = IKCP_RTO_MIN
		self.m_send_win 		 = IKCP_WND_SND
		self.m_receive_win  	 = IKCP_WND_RCV
		self.m_remote_win 		 = IKCP_WND_RCV
		self.m_cwnd 			 = 1
		self.m_increase 		 = 0
		self.m_probe_mask 		 = 0
		self.m_cur_tm 			 = 0
		self.m_interval 	     = IKCP_INTERVAL
		self.m_flush_tm 		 = IKCP_INTERVAL
		self.m_time_out    		 = 0
		self.m_nodelay 			 = 0
		self.m_probe_tm 		 = 0
		self.m_probe_wait 		 = 0
		self.m_dead_link 		 = IKCP_DEADLINK
		self.m_state 			 = 0
		self.m_send_queue        = segment_link()
		self.m_receive_queue     = segment_link()
		self.m_send_buf 		 = segment_link()
		self.m_receive_buf 		 = segment_link()
		self.m_reclaim_link      = segment_link()
		self.m_ack_list 		 = [] 
		self.m_ack_count 		 = 0
		self.m_fast_resend 	     = 0
		self.m_nocwnd 			 = False
		self.m_stream 			 = False
		self.m_log_mask 		 = 0
		self.m_out_put_fun 	     = out_put_fun
		self.m_write_log_fun     = write_log_fun
		self.m_cur_seg 			 = segment_node()
		self.m_cur_seg.m_user_key= user_key
		self.m_buff_array 		 = []
		self.m_array_len 		 = 0
		self.m_big_endian     	 = False #大端

	#设置参数
	def set_nodelay(self,nodelay,interval,fast_resend,nocwnd):
		if nodelay >= 0:
			self.m_nodelay = nodelay
			if self.m_nodelay != 0:
				self.m_min_rto = IKCP_RTO_NDL
			else:
				self.m_min_rto = IKCP_RTO_MIN
		if interval > 0:
			if self.m_interval > 5000:
				self.m_interval = 50000
			elif self.m_interval < 10:
				self.m_interval = 10
			else:
				self.m_interval = interval
		self.m_fast_resend = fast_resend
		self.m_nocwnd = 0 

	#可用窗口大小
	def receive_win_size(self): 
		count = self.m_receive_win - self.m_receive_queue.m_count
		if count >= 0:
			return count
		return 0

	#发送数据
	def output_data(self):
		self.m_out_put_fun(''.join(self.m_buff_array),self.m_user_data)

	#打包 8 位
	def pack_8bit(self,value,buff_array):
		#无符类型
		if value > 127:
			data = struct.pack('B',value)
		else:
			data = struct.pack('b',value)
		buff_array.append(data)

	#解包 8 位
	def unpack_8bit(self,value,start_index,size):
		#暂不考虑负数
		size = start_index + size
		return struct.unpack('B',value[start_index:size])[0],size

	#打包 16 位
	def pack_16bit(self,value,buff_array):
		#无符类型
		if value > 32767:
			data = struct.pack('H',value)
		else:
			data = struct.pack('h',value)
		buff_array.append(data)

	#解包 16 位
	def unpack_16bit(self,value,start_index,size):
		#暂不考虑负数
		size = start_index + size
		return struct.unpack('H',value[start_index:size])[0],size 

	#打包 32 位
	def pack_32bit(self,value,buff_array):
		#无符类型
		if value > 2147483647:
			data = struct.pack('I',value)
		else:
			data = struct.pack('i',value)
		buff_array.append(data)

	#解包 32 位
	def unpack_32bit(self,value,start_index,size):
		#暂不考虑负数
		size = start_index + size
		return struct.unpack('I',value[start_index:size])[0],size 

	#打包 seg
	def pack_seg(self,seg):
		self.pack_32bit(seg.m_user_key,self.m_buff_array)
		self.pack_8bit(seg.m_cmd,self.m_buff_array)
		self.pack_8bit(seg.m_index,self.m_buff_array)
		self.pack_16bit(seg.m_wind_size,self.m_buff_array)
		self.pack_32bit(seg.m_time_stamp,self.m_buff_array)
		self.pack_32bit(seg.m_sequence,self.m_buff_array)
		self.pack_32bit(seg.m_receive_next,self.m_buff_array)
		self.pack_32bit(len(seg.m_data),self.m_buff_array)
		self.m_buff_array.append(seg.m_data)
		self.m_array_len += IKCP_OVERHEAD + len(seg.m_data) 

	#处理发送数据
	def deal_send_data(self):
		if self.m_array_len >= self.m_mtu: 
			self.deal_net_data()

	#发送数据到网络
	def deal_net_data(self):
		self.output_data()
		self.m_buff_array = []
		self.m_array_len  = 0

	#值差
	def value_diff(self,left,right):
		return left - right

	#取较小值
	def value_min(self,left,right):
		if left < right:
			return left
		return right

	#取较大值
	def value_max(self,left,right):
		if left > right:
			return left
		return right

	#取三个数中间值
	def value_middle(self,left,middle,right):
		return self.value_min(self.value_max(left,middle),right)

	#链表是否为空
	def link_empty(self,link):
		return link.m_head == None

	#从链表头部取出取出一个结点
	def head_pop(self,link):
		if link.m_head == None:
			return None
		result = link.m_head
		link.m_head = link.m_head.m_next
		if link.m_head == None:
			link.m_tail = None
		else:
			link.m_head.m_front = None
		link.m_count  -= 1
		result.m_next  = None
		result.m_front = None
		return result

	#尾插法加入一个结点
	def add_tail(self,link,node):
		if link.m_head == None:
			link.m_head = node
			link.m_tail = node
		else:
			link.m_tail.m_next = node
			node.m_front = link.m_tail
			link.m_tail  = node
		link.m_count += 1	

	#头插法加入一个结点
	def add_head(self,link,node):
		if link.m_head == None:
			link.m_head = node
			link.m_tail = node
		else:
			link.m_head.m_front = node
			node.m_next = link.m_head
			link.m_head = node
		link.m_count += 1

	#移除一个结点
	def remove_node(self,link,node):
		if node.m_front == None:
			link.m_head = node.m_next
		else:	
			node.m_front.m_next = node.m_next
		if node.m_next == None:
			link.m_tail = node.m_front
		else:
			node.m_next.m_front = node.m_front
		node.m_next   = None
		node.m_front  = None
		link.m_count -= 1

	#回收一个 seg 结点
	def reclaim_node(self,seg_node):
		seg_node.__init__()
		self.add_tail(self.m_reclaim_link,seg_node)

	#flush data
	def flush_data(self):
		cur_seg 				= self.m_cur_seg
		cur_seg.m_cmd 			= IKCP_CMD_ACK
		cur_seg.m_index 	    = 0
		cur_seg.m_wind_size     = self.receive_win_size()
		cur_seg.m_receive_next  = self.m_receive_next
		cur_seg.m_sequence      = 0
		cur_seg.m_resend_tm     = 0
		#发送 ack
		for i in xrange(self.m_ack_count):
			self.deal_send_data()
			data = self.m_ack_list[i]
			cur_seg.m_sequence   = data.m_sequence
			cur_seg.m_time_stamp = data.m_time_stamp
			self.pack_seg(cur_seg)
		self.m_ack_count = 0
		#远程窗口为 0，要探测窗口
		if self.m_remote_win == 0:
			if self.m_probe_wait == 0:
				self.m_probe_wait = IKCP_PROBE_INIT
				self.m_probe_tm   = self.m_cur_tm + self.m_probe_wait
			elif self.value_diff(self.m_cur_tm,self.m_probe_tm) >= 0:
				self.m_probe_wait += int(self.m_probe_wait/2)
				if self.m_probe_wait > IKCP_PROBE_LIMIT:
					self.m_probe_wait = IKCP_PROBE_LIMIT
				self.m_probe_tm = self.m_cur_tm + self.m_probe_wait
				self.m_probe_mask |= IKCP_ASK_SEND
		else:
			self.m_probe_wait = 0
			self.m_probe_tm   = 0

		if self.m_probe_mask & IKCP_ASK_SEND:
			seg.m_cmd = IKCP_CMD_WASK
			self.deal_send_data()
			self.pack_seg(cur_seg)

		if self.m_probe_mask & IKCP_ASK_TELL:
			self.m_cmd = IKCP_CMD_WINS
			self.deal_send_data()
			self.pack_seg(cur_seg)

		self.m_probe_mask = 0
		cwnd = self.value_min(self.m_send_win,self.m_remote_win)
		if not self.m_nocwnd:
			cwnd = self.value_min(cwnd,self.m_cwnd)
		while self.value_diff(self.m_send_next,self.m_ack_knowledge + cwnd) < 0:
			if self.link_empty(self.m_send_queue):
				break
			one_node = self.head_pop(self.m_send_queue)
			self.add_tail(self.m_send_buf,one_node)
			one_node.m_user_key 	  =	self.m_user_key
			one_node.m_cmd 		 	  = IKCP_CMD_PUSH
			one_node.m_wind_size 	  = cur_seg.m_wind_size
			one_node.m_time_stamp     = self.m_cur_tm
			one_node.m_sequence 	  = self.m_send_next
			self.m_send_next 		 += 1
			one_node.m_receive_next   = self.m_receive_next
			one_node.m_resend_tm      = self.m_cur_tm
			one_node.m_rto            = self.m_rto
			one_node.m_fast_ack 	  = 0
			one_node.m_time_out 	  = 0

		if self.m_fast_resend > 0:
			resend = self.m_fast_resend
		else:
			resend = 0xffffffff

		if not self.m_nodelay:
			rto_min = int(self.m_rto >> 3)
		else:
			rto_min = 0
		is_timeout  = False
		is_repeated = False
		cur_send    = self.m_send_buf.m_head
		while cur_send != None:
			need_send = False
			if cur_send.m_time_out == 0:
				need_send = True
				cur_send.m_time_out += 1
				cur_send.m_resend_tm = self.m_cur_tm + cur_send.m_rto + rto_min
			#超时
			elif self.value_diff(self.m_cur_tm,cur_send.m_resend_tm) >= 0:
				need_send = True
				cur_send.m_time_out += 1
				if self.m_nodelay:
					cur_send.m_rto += self.m_rto 
				else:
					cur_send.m_rto += (self.m_rto/2)
				cur_send.m_resend_tm = self.m_cur_tm + cur_send.m_rto
				is_timeout = True
			elif cur_send.m_fast_ack >= resend:
				need_send = True
				cur_send.m_time_out += 1
				cur_send.m_fast_ack  = 0
				cur_send.m_resend_tm = self.m_cur_tm + cur_send.m_rto
				is_repeated = True

			if need_send:
				cur_send.m_time_stamp   = self.m_cur_tm 
				cur_send.m_wind_size    = cur_seg.m_wind_size
				cur_send.m_receive_next = cur_seg.m_receive_next
				self.deal_send_data()
				self.pack_seg(cur_send)
			if cur_send.m_time_out >= self.m_dead_link:
				self.m_state = -1
			cur_send = cur_send.m_next
		if self.m_array_len > 0:
			self.deal_net_data()
		if is_repeated:
			inflight = self.m_send_next - self.m_ack_knowledge
			self.m_ssthresh = (inflight/2)
			if self.m_ssthresh < IKCP_THRESH_MIN:
				self.m_ssthresh = IKCP_THRESH_MIN
			self.m_cwnd     = self.m_ssthresh + resend
			self.m_increase = self.m_cwnd * self.m_mss

		if is_timeout:
			self.m_ssthresh = (cwnd/2)
			if self.m_ssthresh < IKCP_THRESH_MIN:
				self.m_ssthresh = IKCP_THRESH_MIN 
			self.m_cwnd     = 1
			self.m_increase = self.m_mss

		if self.m_cwnd < 1:
			self.m_cwnd = 1
			self.m_increase = self.m_mss

	#一次可接收数据大小
	def peek_size(self):
		if self.link_empty(self.m_receive_queue):
			return 0
		cur_seg = self.m_receive_queue.m_head
		if cur_seg.m_index == 0:
			return len(cur_seg.m_data)
		#why?
		if m_receive_queue.m_count < cur_seg.m_index + 1:
			return 0
		while cur_seg != None:
			length += len(cur_seg.m_data)	
			if cur_seg.m_index == 0:
				break
			cur_seg = cur_seg.m_next
		return lenght
	
	#用户接收数据
	def recv_data(self):	
		if self.link_empty(self.m_receive_queue):
			return None 
		recover = False
		#接收窗口为 0
		if self.m_receive_queue.m_count >= self.m_receive_win:
			recover = True
		result_data = []
		cur_seg = self.m_receive_queue.m_head
		while cur_seg != None:
			next_node = cur_seg.m_next
			if len(cur_seg.m_data) != 0:
				result_data.append(cur_seg.m_data)
			self.remove_node(self.m_receive_queue,cur_seg)
			if cur_seg.m_index == 0:
				break
			cur_seg = next_node	
		#移动接收缓存数据到接收队列
		while not self.link_empty(self.m_receive_buf):	
			cur_seg = self.m_receive_buf.m_head
			if cur_seg.m_sequence == self.m_receive_next and self.m_receive_queue.m_count < self.m_receive_win:
				self.remove_node(self.m_receive_buf,cur_seg)
				self.add_tail(self.m_receive_queue,cur_seg)
				self.m_receive_next += 1
			else:
				break

		#通告对方有可使用的接收窗口
		if self.m_receive_queue.m_count < self.m_receive_win and recover:
			self.m_probe_mask |= IKCP_ASK_TELL

		return ''.join(result_data)

	#创建一个新结点
	def create_node(self):
		return segment_node()

	#用户发送数据
	def send_data(self,data):
		#流数据 index 都为 0
		surplus_length = len(data)
		use_lenght     = 0 
		if self.m_stream and self.link_empty(self.m_send_queue):
			tail_seg = self.m_send_queue.m_tail
			old_len  = len(tail_seg.m_data)
			capacity = self.m_mss - old_len
			if capacity > 0:
				extend = capacity
				if surplus_length < capacity:
					extend = surplus_length
				tail_seg.m_data = tail_seg.m_data + data[0:extend]
				surplus_length -= extend
				use_lenght 	   += extend
		if surplus_length <= 0:
			return 0
		count = int((surplus_length + self.m_mss - 1)/self.m_mss)
		if count > 255:
			return -2
		#可以没有数据情况
		if count == 0:
			count = 1
		for i in xrange(count):
			size = 0
			if surplus_length > self.m_mss:
				size = self.m_mss
			else:
				size = surplus_length
			new_node = self.create_node()
			if size > 0:
				new_node.m_data = data[use_lenght:use_lenght+size]
			if self.m_stream:
				new_node.m_index = 0 
			else:
				new_node.m_index = count - i - 1
			self.add_tail(self.m_send_queue,new_node)
			surplus_length -= size
			use_lenght 	   += size
		return 0

	#检测 cmd 是否合法
	def check_cmd(self,cmd):
		if cmd != IKCP_CMD_PUSH and cmd != IKCP_CMD_ACK and cmd != IKCP_CMD_WASK and cmd != IKCP_CMD_WINS:
			return False
		return True

	#解析确认序号
	def parse_ack_knowledge(self,ack_knowledge):
		cur_seg = self.m_send_buf.m_head	
		while cur_seg != None:
			next_node = cur_seg.m_next
			if self.value_diff(ack_knowledge,cur_seg.m_sequence) > 0:
				self.remove_node(self.m_send_buf,cur_seg)
				cur_seg = next_node
			else:
				break

	#重新设置确认序号
	def shrink_buf(self):
		if self.link_empty(self.m_send_buf):
			self.m_ack_knowledge = self.m_send_next
		else:
			self.m_ack_knowledge = self.m_send_buf.m_head.m_sequence

	#计算 rto
	def update_rto(self,rtt):
		if self.m_rtt_avg == 0:
			self.m_rtt_avg  = rtt
			self.m_rtt_diff = int(rtt/2)
		else:
			delta = rtt - self.m_rtt_avg
			if delta < 0:
				delta = -delta
			self.m_rtt_diff = int((self.m_rtt_diff*3 + delta)/4)
			self.m_rtt_avg  = int((self.m_rtt_avg*7 + rtt)/8)
			if self.m_rtt_avg < 1:
				self.m_rtt_avg = 1
		rto = self.m_rtt_avg + self.value_max(self.m_interval,self.m_rtt_diff*4)
		self.m_rto = int(self.value_middle(self.m_min_rto,rto,IKCP_RTO_MAX))

	#移除确认包
	def parse_ack(self,sequence):
		cur_seg = self.m_send_buf.m_head
		while cur_seg != None:
			next_node = cur_seg.m_next
			if cur_seg.m_sequence == sequence:
				self.remove_node(self.m_send_buf,cur_seg)
				break
			if cur_seg.m_sequence > sequence:
				break
			cur_seg = next_node 

	#存储 ack
	def push_ack(self,sequence,time_stamp):
		array_len = len(self.m_ack_list)
		if self.m_ack_count >= array_len:	
			new_data = ack_data()
			self.m_ack_list.append(new_data)
		else:
			new_data = self.m_ack_list[self.m_ack_count]
		new_data.m_time_stamp = time_stamp
		new_data.m_sequence   = sequence
		self.m_ack_count += 1

	#解析数据
	def parse_data(self,seg_node):
		cur_node  = self.m_receive_buf.m_head
		repeat = False
		while cur_node != None:	
			if cur_node.m_sequence == seg_node.m_sequence:
				repeat = True
				break
			if self.value_diff(seg_node.m_sequence,cur_node.m_sequence) > 0:
				break
			cur_node = cur_node.m_next
		if not repeat:
			self.add_node(self.m_receive_buf,cur_node,seg_node)

		while not self.link_empty(self.m_receive_buf):
			head_node = self.m_receive_buf.m_head
			if head_node.m_sequence == self.m_receive_next and self.m_receive_queue.m_count < self.m_receive_win: 		
				self.head_pop(self.m_receive_buf)
				self.m_receive_next += 1
				self.add_tail(self.m_receive_queue,head_node)
			else:
				break

	#向链表指定结点前添加结点
	def add_node(self,link,cur_node,new_node):
		#链表为空、当前结点为头结点
		if self.link_empty(link) or cur_node == link.m_head:	
			self.add_head(link,new_node)
		#当前结点为空，表示向后添加
		elif cur_node == None:
			self.add_tail(link,new_node)
		#有当前结点
		else:
			pre_node = cur_node.m_front
			pre_node.m_next.m_front = new_node
			new_node.m_next  = pre_node.m_next
			pre_node.m_next  = new_node
			new_node.m_front = pre_node 
			link.m_count += 1

	#解析重复 ack
	def parse_fastack(self,sequence):
		if self.value_diff(sequence,self.m_ack_knowledge) or self.value_diff(sequence,self.m_send_next) >= 0:
			return
		cur_seg = self.m_send_buf.m_head
		while cur_seg != None:
			if self.value_diff(sequence,cur_seg.m_sequence) < 0:
				break
			elif sequence != cur_seg.m_sequence:
				cur_seg.m_fast_ack += 1

	#kcp 输入数据
	def input_data(self,data):
		surplus_length = len(data)
		use_lenght     = 0 
		if surplus_length < IKCP_OVERHEAD:
			return -1
		flag 	      = False
		maxack  	  = 0
		data_len      = 0
		cur_seg 	  = self.m_cur_seg
		old_ack_knowledge = self.m_ack_knowledge
		while True: 
			if surplus_length < IKCP_OVERHEAD:
				break
			#用户 key
			cur_seg.m_user_key,use_lenght = self.unpack_32bit(data,use_lenght,TYPE_32_LEN)
			if cur_seg.m_user_key != self.m_user_key:
				return -1
			cur_seg.m_cmd,use_lenght  	      = self.unpack_8bit(data,use_lenght,TYPE_8_LEN)
			cur_seg.m_index,use_lenght        = self.unpack_8bit(data,use_lenght,TYPE_8_LEN)
			cur_seg.m_wind_size,use_lenght    = self.unpack_16bit(data,use_lenght,TYPE_16_LEN)
			cur_seg.m_time_stamp,use_lenght   = self.unpack_32bit(data,use_lenght,TYPE_32_LEN)
			cur_seg.m_sequence,use_lenght     = self.unpack_32bit(data,use_lenght,TYPE_32_LEN)
			cur_seg.m_receive_next,use_lenght = self.unpack_32bit(data,use_lenght,TYPE_32_LEN)
			data_len,use_lenght      	      = self.unpack_32bit(data,use_lenght,TYPE_32_LEN)

			surplus_length -= IKCP_OVERHEAD
			if surplus_length < data_len:
				return -2
			if not self.check_cmd(cur_seg.m_cmd):
				return -3
			self.m_remote_win = cur_seg.m_wind_size
			self.parse_ack_knowledge(cur_seg.m_receive_next)
			self.shrink_buf()
			if cur_seg.m_cmd == IKCP_CMD_ACK:
				rtt = self.value_diff(self.m_cur_tm,cur_seg.m_time_stamp)
				if rtt >= 0:
					self.update_rto(rtt)
				self.parse_ack(cur_seg.m_sequence)
				self.shrink_buf()
				if not flag:
					flag   = True
					maxack = cur_seg.m_sequence
				elif self.value_diff(cur_seg.m_sequence,maxack) > 0:
					maxack = cur_seg.m_sequence
			elif cur_seg.m_cmd == IKCP_CMD_PUSH:
				if self.value_diff(cur_seg.m_sequence,self.m_receive_next + self.m_receive_win):
					self.push_ack(cur_seg.m_sequence,cur_seg.m_time_stamp)
					if self.value_diff(cur_seg.m_sequence,self.m_receive_next) >= 0:
						new_seg = self.create_node()
						new_seg.m_user_key     = cur_seg.m_user_key
						new_seg.m_cmd          = cur_seg.m_cmd
						new_seg.m_index        = cur_seg.m_index 
						new_seg.m_wind_size    = cur_seg.m_wind_size
						new_seg.m_time_stamp   = cur_seg.m_time_stamp 
						new_seg.m_sequence     = cur_seg.m_sequence 
						new_seg.m_receive_next = cur_seg.m_receive_next
						if data_len > 0:
							new_seg.m_data = data[use_lenght:data_len + use_lenght]
						self.parse_data(new_seg)
			elif cur_seg.m_cmd == IKCP_CMD_WASK:
				self.m_probe_mask |= IKCP_ASK_TELL
			elif cur_seg.m_cmd == IKCP_CMD_WINS:
				self.m_probe_mask = self.m_probe_mask
			surplus_length -= data_len
			use_lenght 	   += data_len

		flag and self.parse_fastack(maxack)

		sun_alter = self.value_diff(self.m_ack_knowledge,old_ack_knowledge)
		if sun_alter > 0 and self.m_cwnd < self.m_remote_win:
			if self.m_cwnd < self.m_ssthresh:
				self.m_cwnd += 1
				self.m_increase += self.m_mss
			else:
				if self.m_increase < self.m_mss: 
					self.m_increase += self.m_mss
				self.m_increase += int((self.m_mss*self.m_mss)/self.m_increase + self.m_mss/16)
				if (self.m_cwnd + 1) * self.m_mss <= self.m_increase:
					self.m_cwnd += 1
				if self.m_cwnd > self.m_remote_win:
					self.m_cwnd     = self.m_remote_win
					self.m_increase = self.m_remote_win*self.m_mss
		return 0

	#更新函数
	def update(self,cur_tm):
		self.m_cur_tm = cur_tm
		slap = self.value_diff(self.m_cur_tm,self.m_flush_tm)
		if slap >= 10000 or slap <= 10000:	
			slap = 0
			self.m_flush_tm = self.m_cur_tm
		if slap == 0:
			self.m_flush_tm += self.m_interval
			if self.value_diff(self.m_cur_tm,self.m_flush_tm) >= 0:
				self.m_flush_tm = self.m_cur_tm + self.m_interval
			self.flush_data()

	#打印链表所有数据
	def link_display(self,link):
		cur_seg = link.m_head
		while cur_seg != None:
			print(cur_seg.log())
			cur_seg = cur_seg.m_next