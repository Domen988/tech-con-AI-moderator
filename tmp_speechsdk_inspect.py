try:
    import azure.cognitiveservices.speech as speechsdk
    print('sdk loaded', speechsdk.__file__)
    attrs = [a for a in dir(speechsdk.SpeechRecognitionResult) if not a.startswith('_')]
    print(sorted(attrs))
    print('Has duration:', hasattr(speechsdk.SpeechRecognitionResult, 'duration'))
    print('Has offset:', hasattr(speechsdk.SpeechRecognitionResult, 'offset'))
except Exception as e:
    print('ERROR', e)
