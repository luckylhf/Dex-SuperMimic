"""Two-process ROS 2 simulation adapter using the existing Dex motor/IMU messages.

The plant is paced lockstep: it advances only on a complete fresh 29-joint command.
This verifies ROS transport and controller integration, not hard real-time operation.
"""
import argparse
import os
import time
import uuid
import numpy as np
import rclpy
from rclpy.node import Node
from bodyctrl_msgs.msg import MotorCtrl, MotorStatus, MotorStatusMsg, CmdMotorCtrl, Imu
from nav_msgs.msg import Odometry
from dex_supermimic.deployment.runtime import Controller
from dex_supermimic.deployment.native_mujoco import Plant

GROUP_IDS = {'leg': list(range(51,57))+list(range(61,67)), 'waist':[33,32,31],
             'arm':list(range(11,18))+list(range(21,28))}
EXPECTED_NAMES = [f'{joint}_{side}_joint' for side in ('l','r')
                  for joint in ('hip_pitch','hip_roll','hip_yaw','knee_pitch','ankle_pitch','ankle_roll')]
EXPECTED_NAMES += ['waist_yaw_joint','waist_roll_joint','waist_pitch_joint']
EXPECTED_NAMES += [f'{joint}_{side}_joint' for side in ('l','r')
                  for joint in ('shoulder_pitch','shoulder_roll','shoulder_yaw','elbow_pitch','elbow_yaw','wrist_pitch','wrist_roll')]
IDS = GROUP_IDS['leg']+GROUP_IDS['waist']+GROUP_IDS['arm']
INDEX = {motor:i for i,motor in enumerate(IDS)}


class DemoNode(Node):
    def __init__(self, args):
        super().__init__('instanttrack_'+args.mode, namespace='/supermimic_demo')
        self.args = args
        self.controller = Controller(args.bundle, args.reference)
        if self.controller.contract['joint_names'] != EXPECTED_NAMES: raise ValueError('Dex CAN joint order mismatch')
        self.received = {}
        self.imu = None
        self.root_ready = False
        self.session = None
        self.last_activity = time.monotonic()
        if args.mode == 'controller':
            self.cmdpub = {g:self.create_publisher(CmdMotorCtrl, g+'/cmd_ctrl', 10) for g in GROUP_IDS}
            self.subs = [self.create_subscription(MotorStatusMsg, g+'/status', self.state_callback, 10) for g in GROUP_IDS]
            self.subs.append(self.create_subscription(Imu, 'imu/status', self.imu_callback, 10))
            if self.controller.root_feedback:
                self.subs.append(self.create_subscription(Odometry, 'root_feedback', self.root_callback, 10))
        else:
            self.plant = Plant(self.controller)
            self.session = 'instanttrack_sim:'+uuid.uuid4().hex
            self.commands = {}
            self.statepub = {g:self.create_publisher(MotorStatusMsg, g+'/status', 10) for g in GROUP_IDS}
            self.imupub = self.create_publisher(Imu, 'imu/status', 10)
            if self.controller.root_feedback:
                self.rootpub = self.create_publisher(Odometry, 'root_feedback', 10)
            self.subs = [self.create_subscription(CmdMotorCtrl, g+'/cmd_ctrl', self.command_callback, 10) for g in GROUP_IDS]

    def frame_id(self):
        return self.session+':'+str(self.controller.frame)

    def accept_frame(self, frame_id):
        fields = frame_id.split(':')
        if len(fields)!=3 or fields[0]!='instanttrack_sim': return False
        if self.session is None:
            if fields[2]!='0': return False
            self.session = ':'.join(fields[:2])
        return frame_id == self.frame_id()

    def state_callback(self, msg):
        if not self.accept_frame(msg.header.frame_id): return
        for state in msg.status:
            if state.name not in INDEX: raise ValueError('Unknown motor ID')
            self.received[state.name] = (state.pos,state.speed)
        self.maybe_infer()

    def imu_callback(self, msg):
        if not self.accept_frame(msg.header.frame_id): return
        q, w = msg.orientation, msg.angular_velocity
        self.imu = ([q.w,q.x,q.y,q.z],[w.x,w.y,w.z])
        self.maybe_infer()

    def root_callback(self, msg):
        if not self.accept_frame(msg.header.frame_id): return
        p = msg.pose.pose.position
        self.controller.root_position = np.array([p.x,p.y,p.z],dtype=np.float32)
        self.root_ready = True
        self.maybe_infer()

    def maybe_infer(self):
        if len(self.received)!=29 or self.imu is None or (self.controller.root_feedback and not self.root_ready): return
        q = [self.received[x][0] for x in IDS]; qd = [self.received[x][1] for x in IDS]
        tag = self.frame_id(); target = self.controller.step(q, qd, *self.imu)
        c = self.controller.contract
        for group, ids in GROUP_IDS.items():
            msg = CmdMotorCtrl(); msg.header.stamp = self.get_clock().now().to_msg(); msg.header.frame_id = tag
            for motor in ids:
                i = INDEX[motor]; cmd = MotorCtrl(); cmd.name = motor
                cmd.pos=float(target[i]); cmd.kp=float(c['kp'][i]); cmd.kd=float(c['kd'][i]);cmd.spd=0.;cmd.tor=0.
                msg.cmds.append(cmd)
            self.cmdpub[group].publish(msg)
        self.received.clear();self.imu=None;self.root_ready=False;self.last_activity=time.monotonic()

    def command_callback(self, msg):
        if msg.header.frame_id != self.frame_id(): return
        c = self.controller.contract
        for cmd in msg.cmds:
            if cmd.name not in INDEX: raise ValueError('Unknown motor ID')
            i=INDEX[cmd.name]
            values=np.array([cmd.pos,cmd.spd,cmd.tor,cmd.kp,cmd.kd])
            if not np.isfinite(values).all():raise FloatingPointError('Non-finite motor command')
            if abs(cmd.kp-c['kp'][i])>1e-4 or abs(cmd.kd-c['kd'][i])>1e-4 or cmd.spd!=0 or cmd.tor!=0:
                raise ValueError('Command differs from trained PD contract')
            self.commands[cmd.name]=cmd.pos

    def publish_state(self):
        q, qd, quat, gyro = self.plant.sensors(); stamp = self.get_clock().now().to_msg(); tag = self.frame_id()
        for group,ids in GROUP_IDS.items():
            msg=MotorStatusMsg();msg.header.stamp=stamp;msg.header.frame_id=tag
            for motor in ids:
                i=INDEX[motor];state=MotorStatus();state.name=motor;state.pos=float(q[i]);state.speed=float(qd[i]);state.current=0.
                msg.status.append(state)
            self.statepub[group].publish(msg)
        msg=Imu();msg.header.stamp=stamp;msg.header.frame_id=tag
        msg.orientation.w, msg.orientation.x, msg.orientation.y, msg.orientation.z = map(float,quat)
        msg.angular_velocity.x,msg.angular_velocity.y,msg.angular_velocity.z=map(float,gyro)
        self.imupub.publish(msg)
        if self.controller.root_feedback:
            msg=Odometry();msg.header.stamp=stamp;msg.header.frame_id=tag
            pos=self.plant.data.qpos[self.plant.rq:self.plant.rq+3]
            msg.pose.pose.position.x,msg.pose.pose.position.y,msg.pose.pose.position.z=map(float,pos)
            self.rootpub.publish(msg)

    def run_simulation(self):
        start=time.monotonic()
        while not (all(p.get_subscription_count()>0 for p in self.statepub.values()) and self.imupub.get_subscription_count()>0):
            if time.monotonic()-start>15:raise TimeoutError('ROS controller discovery timeout')
            rclpy.spin_once(self,timeout_sec=.02)
        start=time.monotonic();last_publish=0.;latencies=[];late=0
        count=self.controller.frames-1 if self.args.max_steps<=0 else min(self.args.max_steps,self.controller.frames-1)
        for step in range(count):
            self.commands.clear(); sent=time.monotonic();self.publish_state();last_publish=sent
            while len(self.commands)!=29:
                if time.monotonic()-sent>.25:raise TimeoutError('Incomplete/stale 29-joint command')
                rclpy.spin_once(self,timeout_sec=.001)
                if time.monotonic()-last_publish>.04:
                    self.publish_state();last_publish=time.monotonic()
            latency=time.monotonic()-sent;latencies.append(latency*1000)
            if latency>.02:late+=1
            remaining=start+(step+1)*.02-time.monotonic()
            if remaining>0:time.sleep(remaining)
            self.plant.step(np.array([self.commands[x] for x in IDS]))
            self.controller.frame+=1
            if self.plant.measure(self.controller.frame)['failed']:break
        self.plant.save(self.args.out, 'ROS2 separate controller/plant processes, existing Dex motor and IMU message types, CPU MuJoCo, paced lockstep 50 Hz, no support/no reset',
                        {'wall_seconds':time.monotonic()-start,'command_latency_p95_ms':float(np.percentile(latencies,95)),
                         'command_latency_max_ms':float(max(latencies)), 'commands_exceeding_20ms':late,
                         'ros_domain':os.environ['ROS_DOMAIN_ID'],'namespace':'/supermimic_demo',
                         'scope':'ROS integration validation; paced lockstep is not a hard real-time test'})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['controller','sim'],required=True)
    p.add_argument('--bundle',required=True);p.add_argument('--reference',required=True);p.add_argument('--out',required=True)
    p.add_argument('--max-steps',type=int,default=0);a=p.parse_args()
    if os.environ.get('ROS_DOMAIN_ID') not in tuple(str(i) for i in range(215,233)) or os.environ.get('ROS_LOCALHOST_ONLY')!='1':
        raise RuntimeError('This demo requires isolated ROS_DOMAIN_ID 215..232 and ROS_LOCALHOST_ONLY=1')
    rclpy.init();node=None
    try:
        node=DemoNode(a)
        if a.mode=='sim':node.run_simulation()
        else:
            while rclpy.ok() and time.monotonic()-node.last_activity<20:
                rclpy.spin_once(node,timeout_sec=.05)
    finally:
        if node is not None:node.destroy_node()
        if rclpy.ok(): rclpy.shutdown()
