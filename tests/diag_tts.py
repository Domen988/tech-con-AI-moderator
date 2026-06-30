from app.services.tts import tts
import traceback
print('Attempting TTS synth...')
try:
    audio = tts.synthesize_text('Hello, this is a diagnostics test')
    print('Got audio bytes length:', len(audio))
except Exception as e:
    print('EXCEPTION RAISED:')
    traceback.print_exc()
