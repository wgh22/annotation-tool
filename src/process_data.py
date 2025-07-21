#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import argparse
import rosbag
import cv2
import numpy as np
from tqdm import tqdm

def decode_image_from_ros_msg(msg):
    """
    从 ROS 压缩图像消息中解码出 OpenCV 图像。
    :param msg: ROS 压缩图像消息 (sensor_msgs/CompressedImage)
    :return: OpenCV BGR 图像
    """
    try:
        np_arr = np.frombuffer(msg.data, np.uint8)
        return cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    except Exception as e:
        print(f"Error decoding image: {e}")
        return None

def extract_data_from_bag(bag_path, topic, extract_func):
    """
    从指定的 bag 文件和 topic 中提取数据。
    :param bag_path: .bag 文件的路径。
    :param topic: 要读取的 topic 名称。
    :param extract_func: 一个函数，用于从每个消息中提取所需的数据。
    :return: 一个元组 (timestamps, data)，其中 timestamps 是秒的列表，data 是提取的数据列表。
    """
    timestamps = []
    data = []
    if not os.path.exists(bag_path):
        print(f"Warning: Bag file not found at {bag_path}")
        return np.array([]), []

    try:
        with rosbag.Bag(bag_path, 'r') as bag:
            for _, msg, t in bag.read_messages(topics=[topic]):
                timestamps.append(t.to_sec())
                extracted = extract_func(msg)
                if extracted is not None:
                    data.append(extracted)
    except Exception as e:
        print(f"Error reading bag file {bag_path} for topic {topic}: {e}")
        return np.array([]), []
    
    if not timestamps:
        print(f"Warning: No messages found on topic '{topic}' in {bag_path}. Please check the topic name.")

    return np.array(timestamps), data

def interpolate_data(target_ts, source_ts, source_data):
    """
    将源数据插值到目标时间戳。
    :param target_ts: 目标时间戳 (Numpy array)。
    :param source_ts: 源数据时间戳 (Numpy array)。
    :param source_data: 源数据 (Numpy array of shape [N, D])。
    :return: 插值后的数据 (Numpy array of shape [len(target_ts), D])。
    """
    if source_ts.size == 0 or source_data.size == 0:
        if len(source_data.shape) > 1:
             return np.zeros((len(target_ts), source_data.shape[1]))
        else:
             return np.zeros((len(target_ts), 1))

    source_data = source_data.astype(np.float64)
    if len(source_data.shape) == 1:
        source_data = source_data.reshape(-1, 1)
    
    num_features = source_data.shape[1]
    interpolated_data = np.zeros((len(target_ts), num_features))

    for i in range(num_features):
        interpolated_data[:, i] = np.interp(target_ts, source_ts, source_data[:, i])
        
    return interpolated_data

def get_keyboard_intervals(keyboard_bag_path):
    """
    从 keyboard.bag 中提取事件，并生成有效的时间区间。
    - "start": 标记一个段的开始。
    - "stop": 标记一个段的结束。
    - "stop_and_delete": 使前一个 "start" 无效。
    """
    if not os.path.exists(keyboard_bag_path):
        return []

    events = []
    with rosbag.Bag(keyboard_bag_path, 'r') as bag:
        for _, msg, t in bag.read_messages(topics=['keyboard_input']):
            # 直接使用 msg.data，并转换为小写以防万一
            event_type = msg.data.lower()
            if event_type in ["start", "stop", "stop_and_delete"]:
                events.append((t.to_sec(), event_type))

    # 按时间排序事件
    events.sort(key=lambda x: x[0])
    
    intervals = []
    i = 0
    n = len(events)
    while i < n:
        # 寻找 'start' 事件
        if events[i][1] == 'start':
            start_time = events[i][0]
            
            # 查看从当前 'start' 到下一个 'start' 之间的所有事件
            j = i + 1
            sub_events = []
            while j < n and events[j][1] != 'start':
                sub_events.append(events[j])
                j += 1

            # 检查这个区间内是否有 'stop_and_delete'
            has_delete = any(e[1] == 'stop_and_delete' for e in sub_events)
            
            # 如果没有 'stop_and_delete'，则寻找第一个 'stop'
            if not has_delete:
                first_stop = next((e for e in sub_events if e[1] == 'stop'), None)
                if first_stop:
                    intervals.append((start_time, first_stop[0]))
            
            # 将主索引移动到下一个 'start' 事件的位置
            i = j
        else:
            i += 1
            
    return intervals

def map_time_intervals_to_indices(timestamps, intervals):
    """
    将时间区间映射到时间戳数组的索引区间。
    """
    if not intervals:
        return []

    indices_intervals = []
    for start_time, end_time in intervals:
        start_indices = np.where(timestamps >= start_time)[0]
        end_indices = np.where(timestamps <= end_time)[0]
        
        if start_indices.size > 0 and end_indices.size > 0:
            start_idx = start_indices[0]
            end_idx = end_indices[-1]
            if start_idx <= end_idx:
                indices_intervals.append((start_idx, end_idx))
    
    return indices_intervals

def save_data_segment(output_dir, img_data, arm_data, hand_pos_data, hand_force_data, start_idx, end_idx):
    """
    将指定索引区间的数据保存到一个分段子目录中。
    """
    os.makedirs(output_dir, exist_ok=True)

    video_path = os.path.join(output_dir, 'video.mp4')
    arm_txt_path = os.path.join(output_dir, 'arm.txt')
    hand_txt_path = os.path.join(output_dir, 'hand.txt')
    hand_force_txt_path = os.path.join(output_dir, 'hand_force.txt')

    first_image = decode_image_from_ros_msg(img_data[start_idx])
    if first_image is None:
        print(f"Error decoding image for segment. Skipping segment.")
        return
    height, width, _ = first_image.shape
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    video_writer = cv2.VideoWriter(video_path, fourcc, 30, (width, height))

    print(f"  - Generating segment in {os.path.basename(output_dir)} ({end_idx - start_idx + 1} frames)...")
    with open(arm_txt_path, 'w') as arm_file, \
         open(hand_txt_path, 'w') as hand_file, \
         open(hand_force_txt_path, 'w') as hand_force_file:
        
        for i in tqdm(range(start_idx, end_idx + 1), desc=f"Segment {os.path.basename(output_dir)}", leave=False):
            frame = decode_image_from_ros_msg(img_data[i])
            if frame is not None:
                video_writer.write(frame)

            if arm_data.size > 0:
                arm_file.write(' '.join(map(str, arm_data[i])) + '\n')
            if hand_pos_data.size > 0:
                hand_file.write(' '.join(map(str, hand_pos_data[i])) + '\n')
            if hand_force_data.size > 0:
                hand_force_file.write(' '.join(map(str, hand_force_data[i])) + '\n')

    video_writer.release()

def process_directory(source_dir, output_base_path, segment_mode):
    """
    处理单个数据目录，生成视频和文本文件。
    """
    print(f"Processing directory: {source_dir}")

    # --- 1. 定义文件路径和 Topic 名称 ---
    color_img_bag = os.path.join(source_dir, 'realsence_color_img.bag')
    arm_status_bag = os.path.join(source_dir, 'right_arm_status.bag')
    hand_status_bag = os.path.join(source_dir, 'xhand', 'right_hand_status.bag')
    keyboard_bag = os.path.join(source_dir, 'keyboard.bag')

    IMG_TOPIC = 'realsence_color_img'
    ARM_TOPIC = 'right_arm_status'
    HAND_TOPIC = '/xhand/right_hand_status'

    # --- 2. 提取数据 ---
    img_ts, img_data = extract_data_from_bag(color_img_bag, IMG_TOPIC, lambda msg: msg)
    if len(img_ts) == 0:
        print(f"Critical: No image data found in {source_dir}. Skipping.")
        return

    arm_ts, arm_data_list = extract_data_from_bag(arm_status_bag, ARM_TOPIC, lambda msg: list(msg.joint_status))
    hand_ts, hand_data_list = extract_data_from_bag(hand_status_bag, HAND_TOPIC, lambda msg: {
        'pos': msg.hand_states[0].position,
        'force': [np.linalg.norm([fs.calc_force.x, fs.calc_force.y, fs.calc_force.z]) for fs in msg.sensor_states[0].finger_sensor_states]
    })
    
    # --- 3. 数据清理 ---
    if arm_data_list:
        expected_len = len(arm_data_list[0])
        combined = [(ts, d) for ts, d in zip(arm_ts, arm_data_list) if len(d) == expected_len]
        print(f"Found {len(combined)} valid arm states out of {len(arm_data_list)} total.")
        if combined: arm_ts, arm_data_list = zip(*combined)
        else: arm_ts, arm_data_list = [], []
    arm_ts = np.array(arm_ts)
    arm_data = np.array(arm_data_list, dtype=np.float64) if arm_data_list else np.array([])

    if hand_data_list:
        expected_len = len(hand_data_list[0]['force'])
        combined = [(ts, d) for ts, d in zip(hand_ts, hand_data_list) if len(d['force']) == expected_len]
        print(f"Found {len(combined)} valid hand states out of {len(hand_data_list)} total.")
        if combined: hand_ts, hand_data_list = zip(*combined)
        else: hand_ts, hand_data_list = [], []
    hand_ts = np.array(hand_ts)
    if hand_data_list:
        hand_pos_data = np.array([d['pos'] for d in hand_data_list], dtype=np.float64)
        hand_force_data = np.array([d['force'] for d in hand_data_list], dtype=np.float64)
    else:
        hand_pos_data, hand_force_data = np.array([]), np.array([])

    print(f"Found {len(img_ts)} images, {len(arm_ts)} valid arm states, {len(hand_ts)} valid hand states.")

    # --- 4. 数据插值 ---
    print("Interpolating data to image timestamps...")
    interpolated_arm_data = interpolate_data(img_ts, arm_ts, arm_data)
    interpolated_hand_pos = interpolate_data(img_ts, hand_ts, hand_pos_data)
    interpolated_hand_force = interpolate_data(img_ts, hand_ts, hand_force_data)

    # --- 5. 定义要处理的段 ---
    segments_to_process = []
    
    if segment_mode and os.path.exists(keyboard_bag):
        print("Segment mode enabled. Reading keyboard events...")
        time_intervals = get_keyboard_intervals(keyboard_bag)
        
        if time_intervals:
            first_segment_path = f"{output_base_path}_0"
            if os.path.exists(first_segment_path):
                print(f"Segmented output starting with {first_segment_path} already exists. Skipping.")
                return

            indices_intervals = map_time_intervals_to_indices(img_ts, time_intervals)
            for i, (start_idx, end_idx) in enumerate(indices_intervals):
                segment_path = f"{output_base_path}_{i}"
                segments_to_process.append({'path': segment_path, 'start': start_idx, 'end': end_idx})
        else:
            print("Warning: No valid start/stop intervals found in keyboard.bag. Saving as a single file.")
            segment_mode = False

    if not segment_mode:
        if os.path.exists(os.path.join(output_base_path, 'video.mp4')):
             print(f"Output files already exist in {output_base_path}. Skipping.")
             return
        segments_to_process.append({'path': output_base_path, 'start': 0, 'end': len(img_ts) - 1})

    if not segments_to_process:
        print("No data segments to process. Exiting.")
        return

    # --- 6. 循环处理所有定义的段 ---
    print(f"Found {len(segments_to_process)} segment(s) to process for {source_dir}.")
    for segment in segments_to_process:
        save_data_segment(
            output_dir=segment['path'],
            img_data=img_data,
            arm_data=interpolated_arm_data,
            hand_pos_data=interpolated_hand_pos,
            hand_force_data=interpolated_hand_force,
            start_idx=segment['start'],
            end_idx=segment['end']
        )
    print(f"Finished processing for {source_dir}.")


def main():
    parser = argparse.ArgumentParser(description="Process ROS bags to create synchronized video and data files.")
    parser.add_argument('--bag_dir', type=str, default='../bagdata', help='Path to the root directory containing bag subfolders.')
    parser.add_argument('--output_dir', type=str, default='../video', help='Path to the root directory for output files.')
    parser.add_argument('--segment', action='store_true', help='Enable segmenting based on keyboard.bag events.')
    args = parser.parse_args()

    bag_base_dir = os.path.abspath(args.bag_dir)
    output_base_dir = os.path.abspath(args.output_dir)

    if not os.path.isdir(bag_base_dir):
        print(f"Error: Bag data directory not found at {bag_base_dir}")
        sys.exit(1)

    for dir_name in sorted(os.listdir(bag_base_dir)):
        source_path = os.path.join(bag_base_dir, dir_name)
        if os.path.isdir(source_path):
            output_base_path = os.path.join(output_base_dir, dir_name)
            process_directory(source_path, output_base_path, args.segment)

if __name__ == '__main__':
    main()
