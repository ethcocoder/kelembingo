# -*- coding: utf-8 -*-
"""Generate remaining Amharic TTS MP3s for cartela 394-500."""
import os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from gtts import gTTS

AMHARIC = {0:'ዜሮ',1:'አንድ',2:'ሁለት',3:'ሦስት',4:'አራት',5:'አምስት',6:'ስድስት',7:'ሰባት',8:'ስምንት',9:'ዘጠኙ',10:'አስር',20:'ሀያ',30:'ሰላሳ',40:'አርባ',50:'ሃምሳ',60:'ስità ሰላሳ',70:'ሰባሬ'}

def num_amh(n):
    if n in AMHARIC: return AMHARIC[n]
    t=(n//10)*10; o=n%10
    if t in AMHARIC and o in AMHARIC: return AMHARIC[t]+' '+AMHARIC[o]
    return str(n)

d = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'dashboard', 'public', 'audio', 'cartela_bingo')
os.makedirs(d, exist_ok=True)
count = 0
for i in range(394, 501):
    f = os.path.join(d, f'cartela_{i}.mp3')
    if os.path.exists(f):
        continue
    txt = f'ካርтеላ {num_amh(i)} ቢንጎ'
    try:
        gTTS(text=txt, lang='am', slow=False).save(f)
        count += 1
        print(f'{i}: OK')
    except Exception as e:
        print(f'{i}: ERROR {e}')
print(f'Generated {count} files')
