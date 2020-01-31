"""
File with helper functions to modify datasets. Mostly those functions are
only used once.
"""

import cv2
import dlib
import matplotlib.pyplot as plt
import numpy as np
import os
import pathlib
import random
import sys
import bz2
import torch

from PIL import Image
from torchvision import transforms
from torchvision.utils import save_image
from tqdm import tqdm
# from keras.utils import get_file
from ffhq_dataset.face_alignment import image_align
# from ffhq_dataset.landmarks_detector import LandmarksDetector

from dataloader import RAVDESSDataset

HOME = os.path.expanduser('~')

LANDMARKS_MODEL_URL = 'http://dlib.net/files/shape_predictor_68_face_landmarks.dat.bz2'

IMAGE_256_PATH = HOME + '/Datasets/RAVDESS/Image256'
IMAGE_256_CROP_PATH = HOME + '/Datasets/RAVDESS/Image256Crop'
IMAGE_128_PATH = HOME + '/Datasets/RAVDESS/Image128'
LANDMARKS_PATH = HOME + '/Datasets/RAVDESS/Landmarks'
LANDMARKS_128_PATH = HOME + '/Datasets/RAVDESS/Landmarks128'
LANDMARKS_256_PATH = HOME + '/Datasets/RAVDESS/Landmarks256'
LANDMARKS_POINT_IMAGE_128_PATH = HOME + '/Datasets/RAVDESS/LandmarksPointImage128'
LANDMARKS_LINE_IMAGE_128_PATH = HOME + '/Datasets/RAVDESS/LandmarksLineImage128'
VIDEO_PATH = HOME + '/Datasets/RAVDESS/Video'

CELEBA_PATH = HOME + '/Datasets/CELEBA/Imgs'
CELEBA_LANDMARKS_PATH = HOME + '/Datasets/CELEBA/Landmarks'
CELEBA_LANDMARKS_LINE_IMAGE_PATH = HOME + '/Datasets/CELEBA/LandmarksLineImage'


def ravdess_get_mean_std_image(root_path, gray=False):
    root_dir = pathlib.Path(root_path)

    if gray:
        transform_list = [transforms.Grayscale(), transforms.ToTensor()]
    else:
        transform_list = [transforms.ToTensor()]

    transform = transforms.Compose(transform_list)

    # Get all paths
    all_sentences = [p for p in list(root_dir.glob('*/*/'))
                     if str(p).split('/')[-1] != '.DS_Store']
    num_sentences = len(all_sentences)

    # Use only 5 frames from each sentence
    all_frame_paths = []
    for path in all_sentences:
        sentence = list(path.glob('*'))
        random.shuffle(sentence)
        sentence = sentence[:5]
        sentence = [str(path) for path in sentence]
        for s in sentence:
            all_frame_paths.append(s)

    print("{} frames used from {} sentences".format(
        len(all_frame_paths), num_sentences))
    all_frames = []

    for frame_path in all_frame_paths:
        with open(frame_path, 'rb') as file:
            frame = Image.open(file).convert('RGB')
            frame = transform(frame)
            all_frames.append(frame.numpy())

    all_frames = np.array(all_frames)
    print(all_frames.shape)
    print('Mean: {}'.format(all_frames.mean(axis=(0, 2, 3))))
    print('Std: {}'.format(all_frames.std(axis=(0, 2, 3))))


def ravdess_to_frames_center_crop(root_path):
    image_path = IMAGE_256_CROP_PATH
    target_size = 256

    root_dir = pathlib.Path(root_path)

    all_folders = [p for p in list(root_dir.glob('*/'))
                   if str(p).split('/')[-1] != '.DS_Store']

    for i_folder, folder in enumerate(all_folders):
        paths = [str(p) for p in list(folder.glob('*/'))]
        actor = paths[0].split('/')[-2]

        for i_path, path in enumerate(tqdm(paths)):
            utterance = path.split('/')[-1][:-4]
            path_to_utt_img = os.path.join(image_path, actor, utterance)
            print("Utterance {} of {}, actor {} of {}, {}".format(
                i_path + 1, len(paths), i_folder + 1, len(all_folders),
                path_to_utt_img))
            os.makedirs(path_to_utt_img, exist_ok=True)

            # Restart frame counter
            i_frame = 0

            cap = cv2.VideoCapture(path)
            while cap.isOpened():
                # Frame shape: (720, 1280, 3)
                ret, frame = cap.read()
                if not ret:
                    break
                i_frame += 1

                save_str_img = os.path.join(
                    path_to_utt_img, str(i_frame).zfill(3) + '.jpg')

                h, w, c = frame.shape
                new_w = int((w / h) * target_size)
                frame = cv2.resize(frame, (new_w, target_size))

                # print(frame.shape)

                # # Center crop
                # left = (new_w - target_size) // 2
                # right = left + target_size
                # frame = frame[:, left:right]

                # print(frame.shape)

                # Visualize
                cv2.imshow("Output", frame)
                cv2.waitKey(0)

                # Save
                # cv2.imwrite(save_str_img, frame)


def unpack_bz2(src_path):
    data = bz2.BZ2File(src_path).read()
    dst_path = src_path[:-4]
    with open(dst_path, 'wb') as fp:
        fp.write(data)
    return dst_path


def ravdess_align_videos(root_path, actor):
    print("Aligning {}".format(actor))
    # Load landmarks model
    detector = dlib.get_frontal_face_detector()
    predictor = dlib.shape_predictor(
        HOME + '/Datasets/RAVDESS/shape_predictor_68_face_landmarks.dat')

    target_path = HOME + '/Datasets/RAVDESS/Aligned'
    root_dir = pathlib.Path(os.path.join(root_path, actor))
    sentences = [str(p) for p in list(root_dir.glob('*/'))
                 if str(p).split('/')[-1] != '.DS_Store']
    assert len(sentences) > 0

    for i_path, path in enumerate(tqdm(sentences)):
        utterance = path.split('/')[-1][:-4]
        path_to_utt = os.path.join(target_path, actor, utterance)
        print("Utterance {} of {}, {}".format(
            i_path + 1, len(sentences), path_to_utt))
        os.makedirs(path_to_utt, exist_ok=True)

        # Restart frame counter
        i_frame = 0

        cap = cv2.VideoCapture(path)
        while cap.isOpened():
            # Frame shape: (720, 1280, 3)
            ret, frame = cap.read()
            if not ret:
                break
            i_frame += 1
            save_str = os.path.join(path_to_utt, str(i_frame).zfill(3) + '.png')
            if os.path.exists(save_str):
                continue

            # Convert from BGR to RGB
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Pre-resize to save computation
            h_old, w_old, _ = frame.shape
            h_new = 256
            factor = h_new / h_old
            w_new = int(w_old * factor)
            frame_small = cv2.resize(frame, (w_new, h_new))

            # Grayscale image
            gray_small = cv2.cvtColor(frame_small, cv2.COLOR_BGR2GRAY)

            # Detect faces
            for rect in detector(frame_small, 1):
                landmarks = [(int(item.x / factor), int(item.y / factor))
                             for item in predictor(gray_small, rect).parts()]
                image_align(frame, save_str, landmarks)
                break


def ravdess_resize_frames(path_to_actor):
    def downsample_img(img):
        c, h, w = img.shape
        factor = h // 256
        img = img.reshape(c, h // factor, factor, w // factor, factor)
        img = img.mean([2, 4])
        return img

    transform = transforms.ToTensor()
    if path_to_actor[-1] == '/':
        path_to_actor = path_to_actor[:-1]
    new_base_dir = os.path.join('/', *path_to_actor.split('/')[:-2], 'Aligned_256')
    os.makedirs(new_base_dir, exist_ok=True)
    new_dir = os.path.join(new_base_dir, path_to_actor.split('/')[-1])
    os.makedirs(new_dir, exist_ok=True)
    print('Saving to: {}'.format(new_dir))

    all_folders = [str(f) for f in list(pathlib.Path(path_to_actor).glob('*'))]
    all_folders = sorted(all_folders)

    for folder in tqdm(all_folders):
        save_dir = os.path.join(new_dir, folder.split('/')[-1])
        os.makedirs(save_dir, exist_ok=True)
        all_frames = [str(f) for f in pathlib.Path(folder).glob('*')]
        for frame in all_frames:
            save_path = os.path.join(save_dir, frame.split('/')[-1])
            image = transform(Image.open(frame))
            image = downsample_img(image)
            save_image(image, save_path)


def ravdess_convert_to_frames(root_path):
    # Source: https://www.pyimagesearch.com/2017/04/03/facial-landmarks-dlib-opencv-python/
    # initialize dlib's face detector (HOG-based) and then create
    # the facial landmark predictor
    detector = dlib.get_frontal_face_detector()
    predictor = dlib.shape_predictor(
        HOME + '/Datasets/RAVDESS/shape_predictor_68_face_landmarks.dat')

    image_path = IMAGE_256_PATH
    landmarks_path = LANDMARKS_256_PATH
    target_size = 256
    root_dir = pathlib.Path(root_path)

    all_folders = [p for p in list(root_dir.glob('*/'))
                   if str(p).split('/')[-1] != '.DS_Store']

    for i_folder, folder in enumerate(all_folders):
        paths = [str(p) for p in list(folder.glob('*/'))]
        actor = paths[0].split('/')[-2]

        for i_path, path in enumerate(tqdm(paths)):
            utterance = path.split('/')[-1][:-4]
            path_to_utt_img = os.path.join(image_path, actor, utterance)
            path_to_utt_landmarks = os.path.join(landmarks_path, actor, utterance)
            print("Utterance {} of {}, actor {} of {}, {}".format(
                i_path + 1, len(paths), i_folder + 1, len(all_folders),
                path_to_utt_img))
            os.makedirs(path_to_utt_img, exist_ok=True)
            os.makedirs(path_to_utt_landmarks, exist_ok=True)

            # h_ needs to be computed for every utterance
            h = None
            # Restart frame counter
            i_frame = 0

            cap = cv2.VideoCapture(path)
            while cap.isOpened():
                # Frame shape: (720, 1280, 3)
                ret, frame = cap.read()
                if not ret:
                    break
                i_frame += 1

                # Get target file name
                save_str_img = os.path.join(
                    path_to_utt_img, str(i_frame).zfill(3) + '.jpg')
                save_str_landmarks = os.path.join(
                    path_to_utt_landmarks, str(i_frame).zfill(3) + '.jpg')

                # If file already exists, skip
                if os.path.exists(save_str_img):
                    print("Already exists. Skipping...")
                    continue

                # Pre-resize to save computation (1.65 * target_size)
                shape = frame.shape
                w_ = int(1.65 * target_size)  # new ds
                h_ = int((shape[1] / shape[0]) * w_)
                frame = cv2.resize(frame, (h_, w_))

                # Grayscale image
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                # Detect faces
                rects = detector(frame, 1)
                for (i, rect) in enumerate(rects):
                    # Detect landmarks in faces
                    landmarks = predictor(gray, rect)
                    landmarks = shape_to_np(landmarks)

                    # Center of face
                    top_ = min(landmarks[19, 1], landmarks[24, 1])
                    bottom_ = max(landmarks[6:10, 1])
                    left_ = min(landmarks[:4, 0])
                    right_ = max(landmarks[12:16, 0])
                    cx = (left_ + right_) // 2
                    cy = (top_ + bottom_) // 2

                    if h is None:
                        # Top and bottom
                        h = bottom_ - top_
                        # Add margin
                        # margin = int(.35 * h)  # Old ds
                        margin = int(.85 * h)  # new ds
                        h = h + margin

                    # shift cy
                    cy -= int(.15 * h)  # new ds

                # Compute left right
                if cx - (h // 2) < 0:
                    left = 0
                    right = h
                elif cx + (h // 2) > shape[1]:
                    right = shape[1]
                    left = shape[1] - h
                else:
                    left = cx - (h // 2)
                    right = cx + (h // 2)

                # Compute top bottom
                if cy - (h // 2) < 0:
                    top = 0
                    bottom = h
                elif cy + (h // 2) > shape[0]:
                    bottom = shape[0]
                    top = shape[0] - h
                else:
                    top = cy - (h // 2)
                    bottom = cy + (h // 2)

                # # Visualize
                # cv2.rectangle(frame,
                #               (left, top),
                #               (right, bottom),
                #               (0, 0, 255), 1)
                # for (x, y) in landmarks:
                #     cv2.circle(frame, (x, y), 1, (0, 0, 255), -1)
                # cv2.imshow("Output", frame)
                # cv2.waitKey(0)

                # Cut center
                frame = frame[top:bottom, left:right]
                landmarks[:, 0] -= left
                landmarks[:, 1] -= top

                # Resize landmarks
                landmarks[:, 0] = landmarks[:, 0] * (target_size / frame.shape[1])
                landmarks[:, 1] = landmarks[:, 1] * (target_size / frame.shape[0])

                # Resize frame
                frame = cv2.resize(frame, (target_size, target_size))

                # # Visualize 2
                # for (x, y) in landmarks:
                #     cv2.circle(frame, (x, y), 1, (0, 0, 255), -1)
                # cv2.imshow("Output", frame)
                # cv2.waitKey(0)

                # Save
                np.save(save_str_landmarks, landmarks)
                cv2.imwrite(save_str_img, frame)


def ravdess_extract_landmarks(path_to_actor):
    # Source: https://www.pyimagesearch.com/2017/04/03/facial-landmarks-dlib-opencv-python/
    # initialize dlib's face detector (HOG-based) and then create
    # the facial landmark predictor
    detector = dlib.get_frontal_face_detector()
    predictor = dlib.shape_predictor(
        HOME + '/Datasets/RAVDESS/shape_predictor_68_face_landmarks.dat')

    if path_to_actor[-1] == '/':
        path_to_actor = path_to_actor[:-1]
    new_dir_lm = os.path.join('/', *path_to_actor.split('/')[:-2],
                              'Landmarks_Aligned256', path_to_actor.split('/')[-1])
    new_dir_mask = os.path.join('/', *path_to_actor.split('/')[:-2],
                                'Mask_Aligned256', path_to_actor.split('/')[-1])
    os.makedirs(new_dir_lm, exist_ok=True)
    os.makedirs(new_dir_mask, exist_ok=True)
    print('Saving to {} and {}'.format(new_dir_lm, new_dir_mask))

    all_folders = [str(f) for f in list(pathlib.Path(path_to_actor).glob('*'))]
    all_folders = sorted(all_folders)

    for folder in tqdm(all_folders):
        save_dir_lm = os.path.join(new_dir_lm, folder.split('/')[-1])
        save_dir_mask = os.path.join(new_dir_mask, folder.split('/')[-1])
        os.makedirs(save_dir_lm, exist_ok=True)
        os.makedirs(save_dir_mask, exist_ok=True)
        all_frames = [str(f) for f in pathlib.Path(folder).glob('*')
                      if str(f).split('/')[-1] != '.DS_Store']
        for frame in all_frames:
            # load the input image, resize it, and convert it to grayscale
            img = cv2.imread(frame)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            save_path_lm = os.path.join(save_dir_lm, frame.split('/')[-1][:-4] + '.npy')
            save_path_mask = os.path.join(save_dir_mask, frame.split('/')[-1][:-4] + '.png')

            # Detect faces
            rects = detector(img, 1)
            for (i, rect) in enumerate(rects):
                # Detect landmarks in faces
                landmarks = predictor(gray, rect)
                landmarks = shape_to_np(landmarks)

                # Compute mask
                mask = compute_face_mask(landmarks, img)

                # Save
                np.save(save_path_lm, landmarks)

                # Save image
                cv2.imwrite(save_path_mask, mask)


def compute_face_mask(landmarks, image):
    jaw = landmarks[0:17]
    left_eyebrow = landmarks[17:20]
    left_eyebrow[:, 1] = left_eyebrow[:, 1] - 10
    right_eyebrow = landmarks[24:27]
    right_eyebrow[:, 1] = right_eyebrow[:, 1] - 10
    hull = np.concatenate(
        (jaw, np.flip(right_eyebrow, 0), np.flip(left_eyebrow, 0)))
    mask = np.zeros(image.shape, dtype='uint8')
    mask = cv2.drawContours(mask, [hull], -1,
                            (255, 255, 255), thickness=cv2.FILLED)
    mask = cv2.bitwise_not(mask)
    img2gray = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(img2gray, 10, 255, cv2.THRESH_BINARY_INV)
    return mask


def rect_to_bb(rect):
    # Source: https://www.pyimagesearch.com/2017/04/03/facial-landmarks-dlib-opencv-python/
    # take a bounding predicted by dlib and convert it
    # to the format (x, y, w, h) as we would normally do
    # with OpenCV
    x = rect.left()
    y = rect.top()
    w = rect.right() - x
    h = rect.bottom() - y

    # return a tuple of (x, y, w, h)
    return x, y, w, h


def shape_to_np(landmarks, dtype="int"):
    # Source https://www.pyimagesearch.com/2017/04/03/facial-landmarks-dlib-opencv-python/
    # initialize the list of (x, y)-coordinates
    coords = np.zeros((68, 2), dtype=dtype)

    # loop over the 68 facial landmarks and convert them
    # to a 2-tuple of (x, y)-coordinates
    for i in range(0, 68):
        coords[i] = (landmarks.part(i).x, landmarks.part(i).y)

    # return the list of (x, y)-coordinates
    return coords


def ravdess_group_by_utterance(root_path):
    root_dir = pathlib.Path(root_path)

    print(root_dir)

    # Get all paths
    all_actors = [p for p in list(root_dir.glob('*/'))
                  if str(p).split('/')[-1] != '.DS_Store']

    for actor in all_actors:
        print("Processing {}".format(str(actor).split('/')[-1]))
        frames = [str(frame) for frame in list(actor.glob('*'))]
        for i_frame, frame in enumerate(frames):
            new_folder = frame[:-8]
            new_path = os.path.join(new_folder, frame[-7:])
            os.makedirs(new_folder, exist_ok=True)
            os.rename(frame, new_path)


def ravdess_plot_label_distribution(data_path):
    ds = RAVDESSDataset(data_path)
    hist, _ = np.histogram(ds.emotions.numpy(), bins=8)
    hist = hist / len(ds.emotions)
    plt.bar(np.arange(8), hist)
    plt.title("Normalized distribution of RAVDESS dataset")
    plt.xticks(np.arange(8),
               ['neutral', 'calm', 'happy', 'sad', 'angry', 'fearful', 'disgust', 'surprised'])
    # plt.savefig('dist.jpg')
    plt.show()


def ravdess_landmark_to_point_image(data_path):

    target_path = LANDMARKS_POINT_IMAGE_128_PATH
    image_size = 128
    data_dir = pathlib.Path(data_path)

    all_files = [str(p) for p in list(data_dir.glob('*/*/*'))
                 if str(p).split('/')[-1] != '.DS_Store']

    for i_file, file in enumerate(tqdm(all_files)):
        save_dir = os.path.join(target_path, *file.split('/')[-3:-1])
        save_str = os.path.join(save_dir, file.split('/')[-1][:3] + '.jpg')

        # Load landmarks
        landmarks = np.load(file)

        # Create blank image
        img = np.zeros((image_size, image_size, 1), np.uint8)

        # Draw landmarks as circles
        for (x, y) in landmarks:
            cv2.circle(img, (x, y), 1, 255, -1)

        # Visualize
        # cv2.imshow("Output", img)
        # cv2.waitKey(0)

        # Save image
        os.makedirs(save_dir, exist_ok=True)
        cv2.imwrite(save_str, img)


def ravdess_landmark_to_line_image(data_path):
    target_path = LANDMARKS_LINE_IMAGE_128_PATH
    image_size = 128
    data_dir = pathlib.Path(data_path)

    all_files = [str(p) for p in list(data_dir.glob('*/*/*'))
                 if str(p).split('/')[-1] != '.DS_Store']

    for i_file, file in enumerate(tqdm(all_files)):
        save_dir = os.path.join(target_path, *file.split('/')[-3:-1])
        save_str = os.path.join(save_dir, file.split('/')[-1][:3] + '.jpg')

        # Load landmarks
        landmarks = np.load(file)

        # Create blank image
        img = np.zeros((image_size, image_size, 1), np.uint8)

        # Draw face
        img = _draw_face(img, landmarks, 1)

        # Visualize
        cv2.imshow("Output", img)
        cv2.waitKey(0)

        # Save image
        # os.makedirs(save_dir, exist_ok=True)
        # cv2.imwrite(save_str, img)


def _draw_lines(img, points, thickness):
    for index, item in enumerate(points):
        if index == len(points) - 1:
            break
        cv2.line(img, tuple(item), tuple(points[index + 1]), 255, thickness)


def _draw_face(img, landmarks, thickness):
    _draw_lines(img, landmarks[:17], thickness)  # Jaw line
    _draw_lines(img, landmarks[17:22], thickness)  # Right eyebrow
    _draw_lines(img, landmarks[22:27], thickness)  # Left eyebrow
    _draw_lines(img, landmarks[27:31], thickness)  # Nose vertical
    _draw_lines(img, landmarks[31:36], thickness)  # Nose horizontal
    cv2.drawContours(img, [landmarks[36:42]], 0, 255, thickness)  # Right eye
    cv2.drawContours(img, [landmarks[42:48]], 0, 255, thickness)  # Left eye
    cv2.drawContours(img, [landmarks[48:59]], 0, 255, thickness)  # Outer lips
    cv2.drawContours(img, [landmarks[60:]], 0, 255, thickness)  # Inner lips
    return img


def celeba_extract_landmarks(root_path, target_path, line_img_path):
    os.makedirs(target_path, exist_ok=True)
    os.makedirs(line_img_path, exist_ok=True)
    detector = dlib.get_frontal_face_detector()
    predictor = dlib.shape_predictor(
        HOME + '/Datasets/RAVDESS/shape_predictor_68_face_landmarks.dat')

    root_dir = pathlib.Path(root_path)

    all_files = [str(p) for p in list(root_dir.glob('*'))
                 if str(p).split('/')[-1] != '.DS_Store']

    for i_file, file in enumerate(tqdm(all_files)):
        img = cv2.imread(file)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        save_path = os.path.join(
            target_path, file.split('/')[-1][:-4] + '.npy')
        save_line_img_path = os.path.join(
            line_img_path, file.split('/')[-1][:-4] + '.jpg')

        # Detect faces
        rects = detector(img, 1)
        for (i, rect) in enumerate(rects):
            # Detect landmarks in faces
            landmarks = predictor(gray, rect)
            landmarks = shape_to_np(landmarks)
            # Save
            np.save(save_path, landmarks)

            # Visualize
            # for (x, y) in landmarks:
            #     cv2.circle(img, (x, y), 1, (0, 0, 255), -1)
            # cv2.imshow("Output", img)
            # cv2.waitKey(0)

            # Create line img
            line_img = np.zeros_like(gray)
            # Draw face
            line_img = _draw_face(line_img, landmarks, 1)
            # Save image
            cv2.imwrite(save_line_img_path, line_img)

            # Visualize
            # cv2.imshow("Output", line_img)
            # cv2.waitKey(0)


def ravdess_project_to_latent(path_to_actor):
    from my_models.style_gan_2 import Generator
    from projector import Projector

    device = 'cuda' if torch.cuda.is_available() else 'cpu'

    # Load model
    g = Generator(1024, 512, 8, pretrained=True).to(device).train()
    for param in g.parameters():
        param.requires_grad = False

    proj = Projector(g)

    transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize([0.5, 0.5, 0.5], [0.5, 0.5, 0.5])
    ])

    if path_to_actor[-1] == '/':
        path_to_actor = path_to_actor[:-1]
    new_dir = os.path.join('/', *path_to_actor.split('/')[:-2],
                           'Projected', path_to_actor.split('/')[-1])
    os.makedirs(new_dir, exist_ok=True)
    print('Saving to {}'.format(new_dir))

    sentences = [str(f) for f in list(pathlib.Path(path_to_actor).glob('*'))]
    sentences = sorted(sentences)

    mapping = {
        'neutral': '01',
        'calm': '02',
        'happy': '03',
        'sad': '04',
        'angry': '05',
        'fearful': '06',
        'disgust': '07',
        'surprised': '08'
    }
    emotions = [mapping[e] for e in ['neutral', 'calm', 'fearful', 'disgust', 'surprised']]
    sentences = list(filter(lambda s: s.split('/')[-1].split('-')[2]
                            in emotions, sentences))
    print(sentences)
    1 / 0

    for folder in tqdm(sentences):
        save_dir = os.path.join(new_dir, folder.split('/')[-1])
        os.makedirs(save_dir, exist_ok=True)
        all_frames = [str(f) for f in pathlib.Path(folder).glob('*')
                      if str(f).split('/')[-1] != '.DS_Store']
        for i, frame in enumerate(sorted(all_frames)):
            print('Projecting {}'.format(frame))

            save_path = os.path.join(save_dir, frame.split('/')[-1][:-4] + '.pt')

            target_image = Image.open(frame)
            target_image = transform(target_image).to(device)

            # Run projector
            proj.run(target_image, 1000 if i == 0 else 50)

            # Collect results
            latents = proj.get_latents().cpu()
            torch.save(latents, save_path)


if __name__ == "__main__":

    actor = sys.argv[1]

    # ravdess_get_mean_std_image(IMAGE_256_PATH, True)
    # ravdess_extract_landmarks(actor)
    ravdess_project_to_latent(actor)
    # ravdess_group_by_utterance(IMAGE_256_PATH)
    # ravdess_plot_label_distribution(IMAGE_PATH)
    # ravdess_resize_frames(actor)
    # ravdess_align_videos(VIDEO_PATH, actor)
    # ravdess_convert_to_frames(VIDEO_PATH)
    # ravdess_to_frames_center_crop(VIDEO_PATH)
    # ravdess_landmark_to_point_image(LANDMARKS_128_PATH)
    # ravdess_landmark_to_line_image(LANDMARKS_128_PATH)
    # celeba_extract_landmarks(CELEBA_PATH, CELEBA_LANDMARKS_PATH, CELEBA_LANDMARKS_LINE_IMAGE_PATH)