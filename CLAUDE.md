# Project Overview

This repository is a part of a larger project for the grad school course
`EECE5644 - Machine Learning/Pattern Recognition`. The project is worth 20% of
the final grade.

Our project is to build a system that mimics the magic wand functionality found
in the Harry Potter area of Universal Studios. The system will be able to detect
the motion of a wand in a video stream and classify the pattern into one of
multiple predefned gestures (or spells).

## System Design
Our system includes a camera that captures a video stream of the user waving a
wand in front of it. The video stream is processed in real-time to detect the
motion of the wand and generate a pattern of vectors that represent the motion
from each frame. This pattern is then fed to a classifier that has been trained
to recognize a set of predefined gestures (or spells). The detected gesture is
then used to trigger a corresponding action in the system, such as displaying a
visual effect on the screen or playing a sound effect, or physically actuating a
device (physical activation will be done if time permits).

To make the wand detection simple, we plan to use a wand that can easily be
tracked using an OpenCV color filter. The wand will be a brightly colored ping
pong ball attached to a stick. This will allow us to use color filtering to
detect the wand in the video stream, tracking its position across frames.

Broadly speaking, the flow of the system is as follows:

```text 

                      Vision System (OpenCV)
                              |
                              |
                              v
                        Motion Detection
                              |
                              |
                              v
                        Gesture Inference
                              |
                              |
                              v
                        Action Trigger
```

### Vision System (OpenCV)

This subsystem is responsible for capturing the video stream from the camera and
processing it to detect the motion of the wand. It uses OpenCV to perform color
filtering, contour detection, and tracking of the wand's position across
frames. This system will output the position of the tip of the wand (midpoint of
the ping pong ball) in each frame, and the timestamp of each frame.

### Motion Detection

This subsystem receives a stream of timetamped positions of the wand's tip from
the vision system. It processes this stream to generate a pattern of vectors
that represent the motion of the wand. The vector encodes the direction of the
wand's motion between consecutive frames, and the magnitude of the vector
encodes the speed of the wand's motion. The output of this subsystem is a
sequence of vectors that represent the motion of the wand over time.

The motion detection subsystem will also perform motion detection to determine
when the wand is moving and when it is stationary. Each gesture is defined by
"idle" and "motion" states:

**Idle**: A state where the wand is not moving, or moving under some threshold
to account for natural hand tremors.

**Motion**: A state where the wand is moving, and the motion is above a certain
threshold. The threshold is defined as a minimum speed of the wand's tip.

Every valid gesture is bounded by an idle state at the beginning and end of the
gesture. A valid gesture looks like this:
```text
  Idle ->        Motion             ->  Idle
         |<-- Valid Time Window -->|
```

The motion detection subsystem will output a sequence of vectors for every
potentially valid gesture. A valid gesture is defined by a start action that is
triggered by the wand moving above a certain threshold, and an end action that
is triggered by the wand moving below a certain threshold. Additionally, any
motion that either exceeds a certain time window or is too small to be
considered valid will be discarded.

### Gesture Classification

This subsystem receives the sequence of vectors from the motion detection
subsystem and classifies the motion into one of predefined gestures. This will
be done by training a machine learning model on a dataset of labeled gestures.

There will be a minimum threshold of confidence that the classifier must meet in
order to consider a gesture valid. If the confidence is below this threshold,
the gesture will be discarded and no action will be triggered. The output of
this subsystem is the detected gesture, along with the confidence score of the
classification.

### Action Trigger
This subsystem receives the detected gesture from the gesture classification and
triggers the corresponding action in the system. This could be displaying a
visual effect on the screen, playing a sound effect, or physically actuating a
device. The action triggered will depend on the detected gesture and the
confidence score of the classification. If the confidence score is below a
certain threshold, the action will not be triggered, and the user will be
provided some feedback indicating that the gesture was not recognized.

# Project Organization

This is a mono-repo that contains all the code for the project. The project is
organized into components, and each component has its own directory. This
organization will evolve over time, but the current structure is as follows:

- `data-collection`: Contains code for collecting and labeling data for training
  the gesture classifier.

# Standards and Documentation

All development must follow `docs/standards.md`, which covers workflow,
tooling, formatting and documentation rules. The system-wide architecture is in
`docs/architecture.md`.
