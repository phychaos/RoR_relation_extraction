import time
import fitlog

def random_tmp_name():
	#random is useless for seed has been fixed
	a = (time.time() * 1000) % 19260817
	return "tmp_%d.txt" % a
