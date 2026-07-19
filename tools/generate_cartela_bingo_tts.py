"""Generate Amharic TTS MP3s for 'Cartela {number} Bingo'."""
import os
import sys
from gtts import gTTS

AMHARIC_NUMBERS = {
    0: 'ዜሮ',
    1: 'አንድ', 2: 'ሁለት', 3: 'ሦስት', 4: 'አራት', 5: 'አምስት',
    6: 'ስድስት', 7: 'ሰባት', 8: 'ስምንት', 9: 'ዘጠኙ', 10: 'አስር',
    11: 'አስራ አንድ', 12: 'አስራ ሁለት', 13: 'አስራ ሦስት', 14: 'አስራ አራት',
    15: 'አስራ አምስት', 16: 'አስራ ስድስት', 17: 'አስራ ሰባት', 18: 'አስራ ስምንት',
    19: 'አስራ ዘጠኙ', 20: 'ሀያ', 21: 'ሀያ አንድ', 22: 'ሀያ ሁለት', 23: 'ሀያ ሦስት',
    24: 'ሀያ አራት', 25: 'ሀያ አምስት', 26: 'ሀያ ስድስት', 27: 'ሀያ ሰባት',
    28: 'ሀያ ስምንት', 29: 'ሀያ ዘጠኙ', 30: 'ሰላሳ', 31: 'ሰላሳ አንድ',
    32: 'ሰላሳ ሁለት', 33: 'ሰላሳ ሦስት', 34: 'ሰላሳ አራት', 35: 'ሰላሳ አምስት',
    36: 'ሰላሳ ስድስት', 37: 'ሰላሳ ሰባት', 38: 'ሰላሳ ስምንት', 39: 'ሰላሳ ዘጠኙ',
    40: 'አርባ', 41: 'አርባ አንድ', 42: 'አርባ ሁለት', 43: 'አርባ ሦስት',
    44: 'አርባ አራት', 45: 'አርባ አምስት', 46: 'አርባ ስድስት', 47: 'አርባ ሰባት',
    48: 'አርባ ስምንት', 49: 'አርባ ዘጠኙ', 50: 'ሃምሳ', 51: 'ሃምሳ አንድ',
    52: 'ሃምሳ ሁለት', 53: 'ሃምሳ ሦስት', 54: 'ሃምሳ አራት', 55: 'ሃምሳ አምስት',
    56: 'ሃምሳ ስድስት', 57: 'ሃምሳ ሰባት', 58: 'ሃምሳ ስምንት', 59: 'ሃምሳ ዘጠኙ',
    60: 'ስità ሰላሳ', 61: 'ስità ሰላሳ አንድ', 62: 'ስità ሰላሳ ሁለት',
    63: 'ስità ሰላሳ ሦስት', 64: 'ስità ሰላሳ አራት', 65: 'ስità ሰላሳ አምስት',
    66: 'ስità ሰላሳ ስድስት', 67: 'ስità ሰላሳ ሰባት', 68: 'ስità ሰላሳ ስምንት',
    69: 'ስità ሰላሳ ዘጠኙ', 70: 'ሰባሬ', 71: 'ሰባሬ አንድ', 72: 'ሰባሬ ሁለት',
    73: 'ሰባሬ ሦስት', 74: 'ሰባሬ አራት', 75: 'ሰባሬ አምስት',
}

def number_to_amharic(n):
    if n in AMHARIC_NUMBERS:
        return AMHARIC_NUMBERS[n]
    tens = (n // 10) * 10
    ones = n % 10
    if tens in AMHARIC_NUMBERS and ones in AMHARIC_NUMBERS:
        return AMHARIC_NUMBERS[tens] + ' ' + AMHARIC_NUMBERS[ones]
    return str(n)

def generate_cartela_bingo_audio(output_dir, start=1, end=500):
    os.makedirs(output_dir, exist_ok=True)
    total = end - start + 1
    for i, num in enumerate(range(start, end + 1)):
        filepath = os.path.join(output_dir, f'cartela_{num}.mp3')
        if os.path.exists(filepath):
            continue
        amharic_num = number_to_amharic(num)
        text = f'ካርтеላ {amharic_num} ቢንጎ'
        try:
            tts = gTTS(text=text, lang='am', slow=False)
            tts.save(filepath)
            if (i + 1) % 10 == 0 or i == 0:
                print(f'[{i+1}/{total}] Generated cartela_{num}.mp3 ({text})')
        except Exception as e:
            print(f'[{i+1}/{total}] ERROR cartela_{num}.mp3: {e}')
    print(f'Done! Generated {total} files in {output_dir}')

if __name__ == '__main__':
    script_dir = os.path.dirname(os.path.abspath(__file__))
    audio_dir = os.path.join(script_dir, '..', 'dashboard', 'public', 'audio', 'cartela_bingo')
    generate_cartela_bingo_audio(audio_dir)
