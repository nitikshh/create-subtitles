import os
import uuid
from flask import Flask, render_template, request, jsonify, send_from_directory
import yt_dlp
from moviepy.editor import VideoFileClip
import speech_recognition as sr
from pydub import AudioSegment
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import pysrt

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Generate a random secret key

UPLOAD_FOLDER = 'uploaded_videos'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

global_video_filename = None

def download_youtube_video(url, output_path=UPLOAD_FOLDER):
    global global_video_filename

    random_filename = str(uuid.uuid4())
    ydl_opts = {
        'outtmpl': f'{output_path}/{random_filename}.%(ext)s',
        'format': 'bestvideo+bestaudio/best',
        'noplaylist': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            global_video_filename = f"{random_filename}.{info_dict['ext']}"
            print(f"Downloaded: {info_dict['title']}")
            print(f"Saved as: {global_video_filename}")
    except Exception as e:
        print(f"An error occurred: {e}")

def extract_audio_from_video(video_path, audio_path):
    video_clip = VideoFileClip(video_path)
    video_clip.audio.write_audiofile(audio_path)

def transcribe_audio(audio_path, recognizer, language="en", chunk_length_ms=30000, retries=3):
    audio = AudioSegment.from_wav(audio_path)
    chunks = [audio[i:i + chunk_length_ms] for i in range(0, len(audio), chunk_length_ms)]
    transcription = ""

    for i, chunk in enumerate(chunks):
        chunk_path = f"/tmp/chunk_{i}.wav"
        chunk.export(chunk_path, format="wav")
        with sr.AudioFile(chunk_path) as source:
            audio_data = recognizer.record(source)
            attempts = 0
            while attempts < retries:
                try:
                    text = recognizer.recognize_google(audio_data, language=language)
                    transcription += text + " "
                    break
                except sr.UnknownValueError:
                    transcription += "[Unintelligible] "
                    break
                except sr.RequestError as e:
                    attempts += 1
                    if attempts >= retries:
                        transcription += f"[Error: {e}] "
                        break
                    print(f"Retrying transcription... (Attempt {attempts}/{retries})")

        os.remove(chunk_path)

    return transcription.strip()

def split_text_into_segments(text, total_duration, segment_duration=2):
    words = text.split()
    total_words = len(words)
    words_per_segment = max(1, total_words // (total_duration // segment_duration))
    segments = []
    current_segment = []
    current_length = 0

    for word in words:
        current_segment.append(word)
        current_length += 1
        if current_length >= words_per_segment:
            segments.append(' '.join(current_segment))
            current_segment = []
            current_length = 0

    if current_segment:
        segments.append(' '.join(current_segment))

    return segments

def generate_srt(segments, total_duration, segment_duration=2):
    srt_content = []
    for i, segment in enumerate(segments):
        start_time = i * segment_duration * 1000
        end_time = min((i + 1) * segment_duration * 1000, total_duration * 1000)
        srt_content.append(f"{i+1}")
        srt_content.append(f"{format_time(start_time)} --> {format_time(end_time)}")
        srt_content.append(f"{segment}\n")

    return "\n".join(srt_content)

def format_time(milliseconds):
    seconds, milliseconds = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"

def wrap_text(draw, text, font, max_width):
    lines = []
    words = text.split()
    while words:
        line = ''
        while words and draw.textbbox((0, 0), line + words[0], font=font)[2] <= max_width:
            line = f"{line} {words.pop(0)}" if line else words.pop(0)
        lines.append(line)
    return lines

def add_text_to_frame(frame, text, font_path):
    image = Image.fromarray(frame)
    draw = ImageDraw.Draw(image)
    width, height = image.size

    font_size = 40
    font = ImageFont.truetype(font_path, font_size)

    max_text_width = width * 0.9
    lines = wrap_text(draw, text, font, max_text_width)

    line_height = draw.textbbox((0, 0), lines[0], font=font)[3] - draw.textbbox((0, 0), lines[0], font=font)[1]
    total_text_height = (line_height + 10) * len(lines)

    y = height * 0.9 - total_text_height

    for line in lines:
        text_bbox = draw.textbbox((0, 0), line, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        padding = 20
        x = (width - text_width) / 2

        background_x0 = x - padding
        background_y0 = y - 0
        background_x1 = x + text_width + padding
        background_y1 = y + text_height + padding
        draw.rectangle([background_x0, background_y0, background_x1, background_y1], fill=(202, 202, 192))

        draw.text((x, y), line, font=font, fill="white")
        y += line_height + padding

    return np.array(image)

def add_subtitles_to_video(video_path, srt_path, font_path, output_path):
    video = VideoFileClip(video_path)
    subs = pysrt.open(srt_path)

    def process_frame(get_frame, t):
        frame = get_frame(t)
        for sub in subs:
            if sub.start.ordinal / 1000 <= t <= sub.end.ordinal / 1000:
                frame = add_text_to_frame(frame, sub.text, font_path)
        return frame

    new_video = video.fl(process_frame)
    new_video.write_videofile(output_path, codec="libx264", audio_codec="aac")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/create', methods=['POST'])
def create():
    global global_video_filename
    try:
        yt_link = request.form.get('yt_link')
        uploaded_file = request.files.get('uploaded_file')

        response_message = ''
        video_path = ''
        video_with_subtitles_path = ''

        if yt_link:
            download_youtube_video(yt_link)
            if global_video_filename:
                response_message = f"YouTube video saved successfully as {global_video_filename}."
                video_path = os.path.join(UPLOAD_FOLDER, global_video_filename)
            else:
                response_message = "Failed to download YouTube video."
        elif uploaded_file:
            if not os.path.exists(UPLOAD_FOLDER):
                os.makedirs(UPLOAD_FOLDER)

            video_filename = str(uuid.uuid4()) + '_' + uploaded_file.filename
            video_path = os.path.join(UPLOAD_FOLDER, video_filename)
            uploaded_file.save(video_path)
            global_video_filename = video_filename
            response_message = f"File saved successfully as {video_filename}."

        if video_path:
            audio_path = os.path.join(UPLOAD_FOLDER, global_video_filename.rsplit('.', 1)[0] + '.wav')
            extract_audio_from_video(video_path, audio_path)
            recognizer = sr.Recognizer()
            transcription = transcribe_audio(audio_path, recognizer)
            video_duration = int(VideoFileClip(video_path).duration)
            segments = split_text_into_segments(transcription, video_duration)
            srt_content = generate_srt(segments, video_duration)
            srt_path = os.path.join(UPLOAD_FOLDER, global_video_filename.rsplit('.', 1)[0] + '.srt')

            with open(srt_path, 'w') as srt_file:
                srt_file.write(srt_content)

            font_path = "KdamThmorPro-Regular.ttf"
            video_with_subtitles_path = os.path.join(UPLOAD_FOLDER, global_video_filename.rsplit('.', 1)[0] + '_with_subtitles.mp4')
            add_subtitles_to_video(video_path, srt_path, font_path, video_with_subtitles_path)

        # Check if the video file exists
        if not os.path.exists(video_with_subtitles_path):
            raise FileNotFoundError(f"Video file with subtitles not found: {video_with_subtitles_path}")

        return jsonify({
            'message': response_message,
            'video_url': f"/uploaded_videos/{global_video_filename.rsplit('.', 1)[0]}_with_subtitles.mp4"
        })
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'message': 'An error occurred, please try again later.'}), 500


@app.route('/uploaded_videos/<path:filename>', methods=['GET'])
def download_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
