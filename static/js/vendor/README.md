Download the Microsoft Speech SDK bundle to this folder so the app can load it locally and avoid browser Tracking Prevention blocking CDN storage access.

PowerShell (Windows):

    mkdir -Force static\js\vendor
    Invoke-WebRequest -Uri "https://cdn.jsdelivr.net/npm/microsoft-cognitiveservices-speech-sdk/distrib/browser/microsoft.cognitiveservices.speech.sdk.bundle.min.js" -OutFile "static\js\vendor\microsoft.cognitiveservices.speech.sdk.bundle.min.js"

curl (Linux/macOS):

    mkdir -p static/js/vendor
    curl -L -o static/js/vendor/microsoft.cognitiveservices.speech.sdk.bundle.min.js https://cdn.jsdelivr.net/npm/microsoft-cognitiveservices-speech-sdk/distrib/browser/microsoft.cognitiveservices.speech.sdk.bundle.min.js

After downloading, reload the dashboard page. If the file is present, the browser will load the SDK from the local path and avoid Tracking Prevention issues with the CDN.
