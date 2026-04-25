import os
import wave
import sys
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
api_key = os.getenv("DASHSCOPE_API_KEY")
if not api_key:
    print("API Key not found")
    sys.exit(1)

client = OpenAI(
    api_key=api_key,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

wav_file = r"docs\张容权_反无交流.WAV"
out_md = r"docs\张容权_反无交流.md"

if not os.path.exists(wav_file):
    print("File not found")
    sys.exit(1)

CHUNK_DURATION = 50  # seconds

def process_audio():
    with wave.open(wav_file, 'rb') as f:
        frames = f.getnframes()
        rate = f.getframerate()
        channels = f.getnchannels()
        width = f.getsampwidth()
        
        frames_per_chunk = CHUNK_DURATION * rate
        total_chunks = (frames + frames_per_chunk - 1) // frames_per_chunk
        
        print(f"Total chunks to process: {total_chunks}")
        
        with open(out_md, 'w', encoding='utf-8') as md:
            md.write("# 张容权_反无交流 录音转写\n\n")
            md.write("> 注意：录音源包含四川话方言，由阿里云 DashScope SenseVoice-v1 自动识别生成。\n\n")
            
            for i in range(total_chunks):
                chunk_frames = f.readframes(frames_per_chunk)
                if not chunk_frames:
                    break
                
                tmp_filename = f"tmp/chunk_{i}.wav"
                with wave.open(tmp_filename, 'wb') as tmp:
                    tmp.setnchannels(channels)
                    tmp.setsampwidth(width)
                    tmp.setframerate(rate)
                    tmp.writeframes(chunk_frames)
                
                print(f"Processing chunk {i+1}/{total_chunks}...")
                
                try:
                    import time
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            with open(tmp_filename, "rb") as audio_file:
                                transcription = client.audio.transcriptions.create(
                                    model="sensevoice-v1",
                                    file=audio_file,
                                    response_format="text"
                                )
                            break
                        except Exception as e:
                            if attempt == max_retries - 1:
                                raise e
                            print(f"Network error on attempt {attempt+1}, retrying: {e}")
                            time.sleep(2)
                            
                    start_time = i * CHUNK_DURATION
                    mins = start_time // 60
                    secs = start_time % 60
                    
                    text = transcription.strip()
                    md.write(f"**[{mins:02d}:{secs:02d}]** {text}\n\n")
                    md.flush()
                    print(f"[{mins:02d}:{secs:02d}] {text}")
                except Exception as e:
                    print(f"Exception on chunk {i}: {str(e)}")
                    md.write(f"**[{i*CHUNK_DURATION // 60:02d}:{i*CHUNK_DURATION % 60:02d}]** [发生异常: {str(e)}]\n\n")
                finally:
                    if os.path.exists(tmp_filename):
                        try:
                            # Close might be necessary for windows deletion but handled by with block
                            os.remove(tmp_filename)
                        except:
                            pass

if __name__ == "__main__":
    if not os.path.exists("tmp"):
        os.makedirs("tmp")
    process_audio()
    print("Transcription complete.")
