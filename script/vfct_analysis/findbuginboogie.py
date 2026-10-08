#!/usr/bin/python3

import os
import pandas as pd
import subprocess
import shlex
import time
import json
import threading
import re

import sys

CT_ROOT = os.environ.get(
    "CT_ROOT",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
)

# Isolated sites (branch isolated-sites): every leak check
#   havoc $nondet; assert ($nondet ==> e);
# gets the Boogie attribute {:split_here}. Boogie then proves one such
# assertion per VC piece: earlier checks become assumptions and the code
# after the piece's assertion is left out. Line numbers do not change, so
# the mark-by-line flow between step 2 and step 3 is untouched.
# Off unless CT_SPLIT_HERE=1 (the stock single VC is the default; see
# reproduce/ISOLATED_SITES.md for the measurements). CT_VCS_CORES=n lets
# Boogie check n pieces at once.
SPLIT_HERE = os.environ.get("CT_SPLIT_HERE", "0") == "1"
VCS_CORES = os.environ.get("CT_VCS_CORES", "")
BOOGIE_FLAGS = "/doModSetAnalysis /errorLimit 0 /timeLimit 3600"
if VCS_CORES:
    BOOGIE_FLAGS += " /vcsCores:" + VCS_CORES

LEAK_ASSERT = re.compile(r'^(\s*)assert (\(?\$nondet ==>)')

def add_split_here(bplpath):
    """Add {:split_here} to every leak-check assert of bplpath, in place.
    The line count is unchanged. Returns the number of marked asserts."""
    if not SPLIT_HERE:
        return 0
    with open(bplpath, "r") as f:
        lines = f.readlines()
    n = 0
    out = []
    for line in lines:
        new, k = LEAK_ASSERT.subn(r'\1assert {:split_here} \2', line, count=1)
        n += k
        out.append(new)
    with open(bplpath, "w") as f:
        f.writelines(out)
    print("add_split_here: " + bplpath + ": " + str(n) + " leak asserts marked")
    return n
# arg1 前缀名 arg2 bool or shadow

errorline = set()
ress = []
res = []
name = []
boolverif = []
shadowverif = []
vetime = []

def runcommand(command, file = subprocess.PIPE, workdir = os.getcwd()+"/one_and_two_and_three"):
    print(command)
    print("")
    args = shlex.split(command)
    if file != subprocess.PIPE:
        with open(workdir+"/"+file, "w") as f:
            file = f
            st = time.time()
            process = subprocess.Popen(args, stdout=file, stderr=subprocess.PIPE, text=True, cwd=workdir)
            process.wait()
            end = time.time()
    else:
        st = time.time()
        process = subprocess.Popen(args, stdout=file, stderr=subprocess.PIPE, text=True, cwd=workdir)
        process.wait()
        end = time.time()
    
    if(process.returncode != 0):
        print(process.communicate()[1])
    return end - st

def Still_has_false_loop_inv(filename):
	filename = "one_and_two_and_three/" + filename
	file_object = open(filename, 'r')
	try:
		lines = file_object.readlines()
	finally:
		file_object.close()

	errs = r'.*Error:.*This loop invariant might not.*'
	posr = r'bpl\(.*,'
	for line in lines:
		if re.match(errs, line):
			return True
	
	return False 

def readerrorline():
	global errorline
	with open("one_and_two_and_three/errorline.txt","r") as file:
		set_str = file.read()
		if set_str == "":
			my_set = set()
		else:
			my_set = set(map(int, set_str.split(',')))
		errorline = errorline | my_set


def runtillnoerrloopinv(suffix, vertime):
	global res
	totaltime = 0
	global errorline
	errorline = set()
	txtfile = arg1 + "-"+ suffix + "-0"+ ".txt"
	boogiefile = arg1  + "-"+ suffix +"-0" + ".bpl"
	# boogiefile2 = arg1 + "-" + suffix + "-2.bpl"
	add_split_here("one_and_two_and_three/" + boogiefile)
	time = runcommand("boogie " + BOOGIE_FLAGS + " " + boogiefile, txtfile)
	totaltime = totaltime + time
	with open("one_and_two_and_three/vrtime-use.txt","a") as file:
		file.write(f"{time}\t")
		file.write("\n")
		print(time)
		print("\n")
	vertime.append(time)
	# time = runcommand("SecondAnalysis.py " + txtfile +" "+ boogiefile+" " + boogiefile2)
	# totaltime = totaltime + time
	# readerrorline()
	# txtfile = arg1 + "-" + suffix + "-2.txt"
	# time = runcommand("boogie /doModSetAnalysis /errorLimit 0 /timeLimit 3600 " + boogiefile2 ,  txtfile)
	# totaltime = totaltime + time


	item = 0
	while Still_has_false_loop_inv(txtfile):
		boogiefile = arg1 + "-" + suffix +"-" + str(item)  +".bpl"
		boogiefile2 = arg1 + "-" + suffix +"-"+ str(item + 1) +".bpl"
		time = runcommand("SecondAnalysis.py " + txtfile +" "+ boogiefile+" " + boogiefile2)
		totaltime = totaltime + time
		readerrorline()
		txtfile = arg1 + "-" + suffix  + str(item + 1) + ".txt"
		time = runcommand("boogie " + BOOGIE_FLAGS + " " + boogiefile2 ,  txtfile)
		with open("one_and_two_and_three/vrtime-use.txt","a") as file:
			file.write(f"{time}\t")
			file.write("\n")
			print(time)
			print("\n")
		vertime.append(time)
		totaltime = totaltime + time
		item = item + 1
	
	# 在上面的循环中已经做完了最后一次分析
	time = runcommand("geterror_pos_of_boogie_report.py " + txtfile)
	totaltime = totaltime + time
	res.append(totaltime)
	readerrorline()
	#统计一下报错inv 和 asssert个数
	with open("one_and_two_and_three/errorline.txt","r") as file:
		set_str = file.read()
		if set_str == "":
			errshadow = 0
		else:
			my_set = set(map(int, set_str.split(',')))
			errshadow = len(my_set)
		res.append(len(errorline)-errshadow)
		res.append(errshadow)
		res.append(item + 1)
	print("totaltime")
	vetime.append(totaltime)
	return errshadow

def trans_bool_to_shadow():
	global res
	mark = "  assume {:VFCTMarked} true;\n"
	dir = "one_and_two_and_three/"

	tmpshadowfile = arg1 + "-tmp.bpl"
	tshadowfile = arg1+"-tmp-2.bpl"
	shadowfile = arg1 + "-shadow-0.bpl"
	shadowiv = r'.*shadow_invariant.*'
	with open(dir+tmpshadowfile, "r") as file:
		lines = file.readlines()
	
	zancun = []
	with open(dir+tshadowfile, "w") as file:
		for idx, line in enumerate(lines):
			if (idx + 1) in errorline:
				file.write(mark)
				file.write(line)
			else:
				if re.match(shadowiv, line):
					zancun.append(line)
				else:
					if len(zancun) != 0:
						for zc in zancun:
							file.write(zc)
						zancun = []
					file.write(line)
					
					
	
	args = "ruby -I " + os.path.join(CT_ROOT, "bam/bam-991/lib") + " " + os.path.join(CT_ROOT, "bam/bam-991/bin/bam") + " --process_mark " + tshadowfile + " -o " + shadowfile
	time = runcommand(args)
	res.append(time)


def findbuginboogie(args):
	global arg1
	global res
	global vetime
	name.append(args)
	arg1 = args
	res = []
	vetime = []
	numoferror = runtillnoerrloopinv("bool", boolverif)
	if numoferror == 0:
		res.append(0)
		res.append(0)
		res.append(0)
		res.append(0)
	else:
		trans_bool_to_shadow()
		runtillnoerrloopinv("shadow", shadowverif)
	with open('one_and_two_and_three/veriftime.txt', 'w') as file:
		file.write("bool verify time:\n")
		for item in boolverif:
			file.write(f"{item}\t")
		file.write("\n\n")
		file.write("shadow verify time:\n")
		for item in shadowverif:
			file.write(f"{item}\t")
	with open('one_and_two_and_three/'+arg1+'vf.txt', 'w') as file:
		print(vetime)
		for item in vetime:
			file.write(f"{item}\t")
	res.append(vetime[0])
	if(len(vetime) == 1):
		vetime.append(0)
	res.append(vetime[1])
	return res

#运行多个item的版本
# def findbuginboogie(args):
# 	global arg1
# 	for arg in args:
# 		name.append(arg)
# 		arg1 = arg
# 		res = []
# 		runtillnoerrloopinv("bool")
# 		trans_bool_to_shadow()
# 		runtillnoerrloopinv("shadow")
# 		ress.append(res)
# 	return ress
	


if __name__ == "__main__":
	...






	