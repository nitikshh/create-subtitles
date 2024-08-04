from moviepy.editor import VideoFileClip, VideoFileClip, vfx
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import pysrt

def wrap_text(draw, text, font, max_width):
    """Wrap text to fit within a given width when rendered."""
    lines = []
    words = text.split()
    while words:
        line = ''
        while words and draw.textbbox((0, 0), line + words[0], font=font)[2] <= max_width:
            line = f"{line} {words.pop(0)}" if line else words.pop(0)
        lines.append(line)
    return lines

def add_text_to_frame(frame, text, font_path):
    # Convert frame (ndarray) to PIL Image
    image = Image.fromarray(frame)
    draw = ImageDraw.Draw(image)
    width, height = image.size

    # Load the font
    font_size = 40  # Adjust the font size as needed
    font = ImageFont.truetype(font_path, font_size)

    # Calculate max text width (90% of the frame width)
    max_text_width = width * 0.9

    # Wrap the text
    lines = wrap_text(draw, text, font, max_text_width)
    
    # Calculate total text height
    line_height = draw.textbbox((0, 0), lines[0], font=font)[3] - draw.textbbox((0, 0), lines[0], font=font)[1]
    total_text_height = (line_height + 10) * len(lines)  # 10 pixels padding between lines

    # Calculate the initial y position (move subtitles up to ensure visibility of long texts)
    y = height * 0.9 - total_text_height  # 90% above from the bottom

    # Draw each line of text on the image
    for line in lines:
        text_bbox = draw.textbbox((0, 0), line, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        padding = 20
        x = (width - text_width) / 2

        # Draw the background rectangle
        background_x0 = x - padding
        background_y0 = y - 0
        background_x1 = x + text_width + padding
        background_y1 = y + text_height + padding
        draw.rectangle([background_x0, background_y0, background_x1, background_y1], fill=(202, 202, 192))  # Light black background with transparency

        # Draw the text on the image
        draw.text((x, y), line, font=font, fill="white")
        
        # Update y position for next line
        y += line_height + padding

    # Convert PIL Image back to ndarray
    return np.array(image)

def add_subtitles_to_video(video_path, srt_path, font_path, output_path):
    # Load the video
    video = VideoFileClip(video_path)

    # Load the subtitles
    subs = pysrt.open(srt_path)

    # Create a function that adds subtitles to each frame
    def process_frame(get_frame, t):
        frame = get_frame(t)
        for sub in subs:
            if sub.start.ordinal / 1000 <= t <= sub.end.ordinal / 1000:
                frame = add_text_to_frame(frame, sub.text, font_path)
        return frame

    # Apply the function to the video
    new_video = video.fl(process_frame)

    # Write the result to a file
    new_video.write_videofile(output_path, codec="libx264", audio_codec="aac")

# Example usage
video_path = "input_video.mp4"
srt_path = "subtitles.srt"
font_path = "KdamThmorPro-Regular.ttf"
output_path = "output_video_with_subtitles.mp4"

add_subtitles_to_video(video_path, srt_path, font_path, output_path)