import subprocess
import tempfile
import os
import argparse

def findSilences(filename, noise_tolerance, duration):
    command = ["ffmpeg",
               "-i", filename,
               "-af", "silencedetect=n=" + str(noise_tolerance) +
                      ":d=" + str(duration),
               "-f", "null", "-"]
    output = str(subprocess.run(command,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE))
    lines = output.replace("\\r", "").split("\\n")

    time_list = []
    for line in lines:
        if ("silencedetect" in line):
            words = line.split(" ")
            for i in range(len(words)):
                if "silence_start" in words[i]:
                    time_list.append(float(words[i + 1]))
                if "silence_end" in words[i]:
                    time_list.append(float(words[i + 1]))

    return time_list

def getVideoDuration(filename: str) -> float:
    command = ["ffprobe", "-i", filename, "-v", "quiet",
               "-show_entries", "format=duration", "-hide_banner",
               "-of", "default=noprint_wrappers=1:nokey=1"]

    output = subprocess.run(command, stdout=subprocess.PIPE)
    s = str(output.stdout, "UTF-8")
    return float(s)

def getSectionsOfNewVideo(silences, duration):
    return [0.0] + silences + [duration]

def ffmpeg_filter_getSegmentFilter(videoSectionTimings, margin):
    ret = ""
    for i in range(int(len(videoSectionTimings) / 2)):
        start = max(videoSectionTimings[2 * i] - margin, videoSectionTimings[0])
        end = min(videoSectionTimings[2 * i + 1] + margin, videoSectionTimings[-1])
        ret += "between(t," + str(start) + "," + str(end) + ")+"
    ret = ret[:-1]
    return ret

def getFileContent_videoFilter(videoSectionTimings, margin):
    ret = "select='"
    ret += ffmpeg_filter_getSegmentFilter(videoSectionTimings, margin)
    ret += "', setpts=N/FRAME_RATE/TB"
    return ret

def getFileContent_audioFilter(videoSectionTimings, margin):
    ret = "aselect='"
    ret += ffmpeg_filter_getSegmentFilter(videoSectionTimings, margin)
    ret += "', asetpts=N/SR/TB"
    return ret

def writeFile(filename, content):
    with open(filename, "w") as file:
        file.write(str(content))

def ffmpeg_run(file, videoFilter, audioFilter, outfile, fps=60, crf=23, codec='libx264', audio_delay=0):
    videoFilter_file = os.path.join(tempfile.gettempdir(), os.urandom(24).hex())
    audioFilter_file = os.path.join(tempfile.gettempdir(), os.urandom(24).hex())
    open(videoFilter_file, "x").close()
    open(audioFilter_file, "x").close()

    writeFile(videoFilter_file, videoFilter)
    writeFile(audioFilter_file, audioFilter)

    command = [
        "ffmpeg",
        "-i", file,
        "-filter_complex_script:v", videoFilter_file,
        "-filter_complex_script:a", audioFilter_file,
        "-r", str(fps),
        "-crf", str(crf),
        "-c:v", codec,
        "-itsoffset", str(audio_delay / 1000),
        "-i", file,
        "-map", "0:v", "-map", "1:a",
        outfile
    ]
    subprocess.run(command)

    os.remove(videoFilter_file)
    os.remove(audioFilter_file)

def cut_silences(infile, outfile, noise_tolerance, silence_min_duration, margin, audio_delay=0):
    print("Detecting silences, this may take a while depending on the length of the video...")
    silences = findSilences(infile, noise_tolerance, silence_min_duration)
    duration = getVideoDuration(infile)
    videoSegments = getSectionsOfNewVideo(silences, duration)

    videoFilter = getFileContent_videoFilter(videoSegments, margin)
    audioFilter = getFileContent_audioFilter(videoSegments, margin)

    print("Creating new video...")
    ffmpeg_run(infile, videoFilter, audioFilter, outfile, audio_delay=audio_delay)

def main():
    parser = argparse.ArgumentParser(
        description='Automatically detect and cut silences from videos.')
    parser.add_argument("input_file", help="The file that should have the silences cut from it")
    parser.add_argument("-o", "--output_file", help="Where the resulting video should be stored")
    parser.add_argument("-n", "--noise_tolerance", default="0.03",
                        help=("The threshold for determining wether audio is considered silence. "
                              "Can be specified in dB (in case 'dB' is appended to the specified value) "
                              "or amplitude ratio. Default is 0.03"))
    parser.add_argument("-d", "--min_duration", default="0.1",
                        help=("The minimum duration (in seconds) for a silence to be detected as such. "
                              "Default is 0.1"))
    parser.add_argument("-m", "--margin", type=float, default=0.0,
                        help=("The margin (in seconds) that should be kept before and after a non-silent part. "
                              "Should not be larger than half of the minimum duration. "
                              "Default is 0.0"))
    parser.add_argument("-ad", "--audio_delay", type=float, default=0,
                        help=("Audio delay in milliseconds to sync audio and video. Default is 0"))
    args = parser.parse_args()

    if (not os.path.isfile(args.input_file)):
        print("error: The input file could not be found:\n" + args.input_file)
        return

    if (args.margin > (float(args.min_duration) / 2)):
        print("error: The margin is greater than half of the minimum duration\n")
        return

    outfile = args.output_file
    if not outfile:
        tmp = os.path.splitext(args.input_file)
        outfile = tmp[0] + "_cut" + tmp[1]

    cut_silences(args.input_file, outfile, args.noise_tolerance, args.min_duration, args.margin, args.audio_delay)

if __name__ == "__main__":
    main()