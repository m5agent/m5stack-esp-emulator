import os,json,hashlib,binascii,M5
M5.begin()
s=M5.Display
s.setBrightness(255)
s.fillScreen(0)
with open('assets/pixel.png','rb') as f:
 data=f.read()
cwd=os.getcwd()
absolute=cwd+'/assets/pixel.png'
s.drawImage(absolute,8,8)
s.drawImage('assets/pixel.png',40,8)
s.drawImage(data,72,8)
s.drawPng(absolute,104,8)
s.drawPng('assets/pixel.png',136,8)
s.drawPng(data,168,8)
print('IMAGE_PATH_DIAGNOSTIC',json.dumps({'cwd':cwd,'length':len(absolute),'bytes':len(data),'sha256':binascii.hexlify(hashlib.sha256(data).digest()).decode()}))
