import pyglet
import time
import numpy as np
import threading
from collections import deque
from vision import SSLVisionDataProvider

BALL_POS_HISTORY_LENGTH = 20
BALL_LOST_TIME = .1
ROBOT_POS_HISTORY_LENGTH = 20
ROBOT_LOST_TIME = .2

class GameState(object):
    """Game state contains all the relevant information in one place. Many
       threads can edit or use the game state at once, cuz Python GIL
       Since we are using python and types are flexible, a data formats will
       be unofficially specified in the fields below.
    """
    def __init__(self):
        # NOTE: in general fields with underscores are "private" so
        # should only be accessed through getter and setter methods

        # RAW POSITION DATA (updated by vision data or simulator)
        # [most recent data is stored at the front of the queue]
        # ball positions are in the form (x, y)
        self._ball_position = deque([], BALL_POS_HISTORY_LENGTH) # queue of (time, pos)
        # robot positions are (x, y, w) where w = rotation
        self._robot_positions = dict() # Robot ID: queue of (time, pos)
        # TODO: store both teams robots
        # TODO: include game states/events, such as time, score and ref events (see docs)

        # Commands data (desired robot actions)
        # waypoint = (pos, min_speed, max_speed)
        self.robot_waypoints = dict()  # Robot ID: [waypoint] (list of waypoints)
        self.robot_dribblers = dict()  # Dict of dribbler speeds for robot_id
        self.robot_chargings = dict()  # Dict of kicker charging (bool) for robot_id
        self.robot_kicks = dict()  # Dict of kicker discharging commands (bool) for robot_id

        # TODO: cached analysis data (i.e. ball trajectory)
        # this can be later, for now just build the functions
        self.ball_velocity = (0,0)

        # gamestate thread is for doing analysis on raw data (i.e. trajectory calcuations, etc.)
        self._is_analyzing = False
        self._analysis_thread = None

    def start_analyzing(self):
        self._is_analyzing = True
        self._analysis_thread = threading.Thread(target=self.analysis_loop)
        self._analysis_thread.start()

    def analysis_loop(self):
        while self._is_analyzing:
            # TODO: calculate from the position history
            self.ball_trajectory = (1, 1)
            # yield to other threads - run this loop at most 20 times per second
            time.sleep(.05)

    def stop_analyzing(self):
        self._is_analyzing = False
        self._analysis_thread.join()
        self._analysis_thread = None

    # RAW DATA GET/SET FUNCTIONS
    # returns position ball was last seen at
    def get_ball_position(self):
        if len(self._ball_position) == 0:
            # print("getting ball position but ball never seen?!?")
            return None
        timestamp, pos = self._ball_position[0]
        return pos

    def update_ball_position(self, pos):
        self._ball_position.appendleft((time.time(), pos))

    def get_ball_last_update_time(self):
        if len(self._ball_position) == 0:
            # print("getting ball update time but ball never seen?!?")
            return None
        timestamp, pos = self._ball_position[0]
        return timestamp

    def is_ball_lost(self):
        last_update_time = self.get_ball_last_update_time()
        if last_update_time is None:
            return True
        return time.time() - last_update_time > BALL_LOST_TIME

    def get_blue_team_robot_ids(self):
        # UDPATE WHEN INCLUDE YELLOW TEAM
        return tuple(self._robot_positions.keys())

    # returns position robot was last seen at
    def get_robot_position(self, robot_id):
        if robot_id not in self._robot_positions:
            # print("getting position of robot never seen?!?")
            return None
        timestamp, pos = self._robot_positions[robot_id][0]
        return pos

    def update_robot_position(self, robot_id, pos):
        if robot_id not in self._robot_positions:
            self._robot_positions[robot_id] = deque([], ROBOT_POS_HISTORY_LENGTH)
        self._robot_positions[robot_id].appendleft((time.time(), pos))

    def get_robot_last_update_time(self, robot_id):
        if robot_id not in self._robot_positions:
            # print("getting update time of robot never seen?!?")
            return None
        timestamp, pos = self._robot_positions[robot_id][0]
        return timestamp

    def is_robot_lost(self, robot_id):
        last_update_time = self.get_robot_last_update_time(robot_id)
        if last_update_time is None:
            return True
        return time.time() - last_update_time > ROBOT_LOST_TIME

    # ANALYSIS FUNCTIONS
    # basic helper functions - should these be elsewhere?
    def diff_pos(self, p1, p2):
        x = p1[0] - p2[0]
        y = p1[1] - p2[1]

        return (x,y)

    def sum_pos(self, p1, p2):
        x = p1[0] + p2[0]
        y = p1[1] + p2[1]

        return (x,y)

    def scale_pos(self, pos, factor):
        return (pos[0] * factor, pos[1] * factor)

    # TODO - calculate based on robot locations and rules
    def is_position_open(self, pos):
        return True

    # Here we find ball velocities from ball position data
    def get_ball_velocity(self):

        prev_velocity = self.ball_velocity

        positions = self._ball_position
        MIN_TIME_INTERVAL = .05
        i = 0
        if len(positions) <= 1:
            return (0, 0)
        # 0 is most recent!!!
        while i < len(positions) - 1 and  positions[0][0] - positions[i][0] < MIN_TIME_INTERVAL:
            i += 1

        delta_pos = self.diff_pos(positions[0][1], positions[i][1])
        delta_time = (positions[0][0] - positions[i][0])

        self.ball_velocity = self.scale_pos(delta_pos, 1 / delta_time)

        return self.ball_velocity


    def get_ball_pos_future(self, seconds):
        accel_constant = (-.5, -.5)
        # acceleration due to friction as the ball rolls. This number should be tuned empitically.
        velocity_initial = self.get_ball_velocity(self._ball_positions)
        predicted_pos_change = sum_pos(scale(accel_constant, seconds * seconds), scale(velocity_initial, seconds))
        predicted_pos = sum_pos(predicted_pos_change, get_ball_position())
        return predicted_pos
