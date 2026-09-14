#!/usr/bin/python3
import sys
import re
arg1 = sys.argv[1]
# Optional 2nd arg (legacy printer mode); find-bug driver uses 1-arg mode
# that writes errorline.txt for findbuginboogie.py
def run():
	poss = set()
	file_object = open(arg1, 'r')
	try:
		lines = file_object.readlines()
	finally:
		file_object.close()

	errs = r'.*Error:.*This assertion might not.*'
	posr = r'bpl\(.*,'
	for line in lines:
		if re.match(errs, line):
			tar = re.search(posr, line).group()
			pos = re.sub(r'\D',"",tar)
			poss.add(int(pos))

	if len(sys.argv) >= 3:
		arg2 = sys.argv[2]
		print(len(poss))
		poss_sorted = sorted(poss)
		file_object = open(arg2, 'r')
		try:
			blines = file_object.readlines()
		finally:
			file_object.close()
		for i in poss_sorted:
			print(i)
			print(blines[i-1])
		return

	set_str = ','.join(map(str, poss))
	with open("errorline.txt", "w") as file:
		file.write(set_str)

run()
