#! /usr/bin/env python
from PIL import Image, UnidentifiedImageError
import pyexiv2
import uuid
import xml.dom.minidom
import sys
import subprocess
import math
import os
import re

sys.path.append("/data/project/datbot/Tasks/NonFreeImageResizer")
svgMatch = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*(px|in|cm|mm|pt|pc|%)?")

# CC-BY-SA Theopolisme, DatGuy
# Task 3 on DatBot


def parseLength(value):
    # Adapted from https://github.com/Zverik/svg-resize/blob/master/svg_resize.py
    if not value:
        return 0.0
    parts = svgMatch.match(value)
    if not parts:
        raise Exception('Unknown length format: "{}"'.format(value))
    num = float(parts.group(1))
    units = parts.group(2) or "px"
    if units == "px":
        return num
    elif units == "pt":
        return num * 1.25
    elif units == "pc":
        return num * 15.0
    elif units == "in":
        return num * 90.0
    elif units == "mm":
        return num * 3.543307
    elif units == "cm":
        return num * 35.43307
    elif units == "%":
        return -num / 100.0
    else:
        raise Exception("Unknown length units: {}".format(units))


def calculateNewSize(origWidth, origHeight):
    newWidth = int(math.sqrt((100000.0 * origWidth) / origHeight))
    widthPercent = newWidth / origWidth
    newHeight = int(origHeight * widthPercent)

    originalPixels = origWidth * origHeight
    modifiedPixels = newWidth * newHeight
    percentChange = 100.0 * (originalPixels - modifiedPixels) / float(originalPixels)
    return newWidth, newHeight, percentChange


def updateMetadata(sourcePath, destPath, image):
    """This function moves the metadata
    from the old image to the new, reduced
    image using pyexiv2.
    """
    sourceImage = pyexiv2.metadata.ImageMetadata(sourcePath)
    sourceImage.read()
    destImage = pyexiv2.metadata.ImageMetadata(destPath)
    destImage.read()
    sourceImage.copy(destImage)
    destImage["Exif.Photo.PixelXDimension"] = image.size[0]
    destImage["Exif.Photo.PixelYDimension"] = image.size[1]
    destImage.write()


def downloadImage(randomName, origName, site):
    """This function creates the new image, runs
    metadata(), and passes along the new image's
    random name.
    """
    extension = os.path.splitext(origName)[1]
    extensionLower = extension[1:].lower()
    fullName = randomName + extension

    if extensionLower == "gif":
        return "SKIP"
    mwImage = site.Images[origName]

    tempFile = str(uuid.uuid4()) + extension
    with open(tempFile, "wb") as f:
        mwImage.download(f)
    try:
        # Maybe move this all to seperate functions?
        if extensionLower == "svg":
            subprocess.check_call(
                "scour -i {} --enable-viewboxing --enable-id-stripping "
                "--shorten-ids --indent=none".format(tempFile)
            )
            docElement = xml.dom.minidom.parse(tempFile).documentElement
            oldWidth = parseLength(docElement.getAttribute("width"))
            oldHeight = parseLength(docElement.getAttribute("height"))

            viewboxArray = re.split("[ ,\t]+", docElement.getAttribute("viewBox"))
            viewboxOffsetX, viewboxOffsetY = 0, 0

            if oldHeight == 0.0 and oldWidth == 0.0:
                viewboxOffsetX = parseLength(viewboxArray[0])
                viewboxOffsetY = parseLength(viewboxArray[1])
                oldHeight = parseLength(viewboxArray[2])
                oldWidth = parseLength(viewboxArray[3])

            newWidth, newHeight, percentChange = calculateNewSize(oldWidth, oldHeight)
            if percentChange < 5:
                print("Looks like we'd have a less than 5% change "
                      "in pixel counts. Skipping.")
                return "PIXEL"

            docElement.setAttribute("width", str(newWidth))
            docElement.setAttribute("height", str(newHeight))
            docElement.setAttribute(
                "viewBox",
                "{} {} {} {}".format(
                    viewboxOffsetX, viewboxOffsetY, newWidth, newHeight
                ),
            )

            with open(fullName, "wb") as f:
                docElement.writexml(f, encoding="utf-8")

        else:
            img = Image.open(tempFile)
            imgWidth = img.size[0]
            imgHeight = img.size[1]
            if (imgWidth * imgHeight) > 80000000:
                img.close()
                return "BOMB"

            newWidth, newHeight = calculateNewSize(imgWidth, imgHeight)
            if percentChange < 5:
                img.close()
                print("Looks like we'd have a less than 5% change in pixel counts. Skipping.")
                return "PIXEL"

            originalMode = img.mode
            if originalMode in ["1", "L", "P"]:
                img = img.convert("RGBA")

            img = img.resize((int(newWidth), int(newHeight)), Image.ANTIALIAS)
            if originalMode in ["1", "L", "P"]:
                img = img.convert(originalMode, palette=Image.ADAPTIVE)

            img.save(fullName, **img.info, quality=95)

    except UnidentifiedImageError as e:
        print("Unable to open image {0} - aborting ({1})".format(origName, e))
        return "ERROR"
    except IOError as e:
        print("Unable to open image {0} - aborting ({1})".format(origName, e))
        return "ERROR"

    print("Image saved to disk at {0}{1}".format(randomName, extension))

    try:
        updateMetadata(tempFile, fullName, img)  # pyexiv2, see top
        print("Image EXIF data copied!")
    except (IOError, ValueError) as e:
        print("EXIF copy failed. Oh well - no pain, no gain. {0}".format(e))

    filelist = [f for f in os.listdir(".") if f.startswith(tempFile)]
    for fa in filelist:
        os.remove(fa)

    return fullName
