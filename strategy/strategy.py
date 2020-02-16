import threading
import traceback
import numpy as np
import time
from multiprocessing import Queue
import logging

logger = logging.getLogger(__name__)

# import lower-level strategy logic that we've separated for readability
try:
    from utils import Utils
    from analysis import Analysis
    from actions import Actions
    from routines import Routines
    from roles import Roles
    from plays import Plays
    from coaches import *
except (SystemError, ImportError):
    from .utils import Utils
    from .actions import Actions
    from .routines import Routines
    from .roles import Roles
    from .analysis import Analysis
    from .coaches import *
    from .plays import Plays


class Strategy(Utils, Analysis, Actions, Routines, Roles, Plays):
    """
    Control loop for playing the game. Calculate desired robot actions,
    and then sends commands into the gamestate thread using a queue
    in order to control the game.
    """
    def __init__(self, team, simulator=None):
        assert(team in ['blue', 'yellow'])
        self._team = team
        self._data_in_q = Queue()
        self._commands_out_q = Queue()

        self._is_controlling = False
        self._control_thread = None
        self._mode = None
        self._simulator = simulator
        
        # state for reducing frequency of expensive calls
        # (this also helps reduce oscillation)
        self._last_RRT_times = {}  # robot_id : timestamp
    
    def _get_new_gamestate(self):
        """Fetches new gamestate from the separate gamestate process.
        This call will may block until the new gamestate actually
        finishes being returned.
        """
        return self._data_in_q.get()

    def start_controlling(self, mode, loop_sleep):
        """Spins up control process specified by mode, to command the robots"""
        self._control_process = Process(target=self.control_loop, 
            args=(self._command_queue, self._gs_update_queue))
        self._mode = mode
        self._control_loop_sleep = loop_sleep
        self._is_controlling = True
        
        print(f"Running strategy for {self._team} team, mode: {self._mode}")

        if self._mode == "UI":
            print("""
            Using UI Controls!
            Robots:
            - Click to select
            - Click to set goal position (drag for direction)
            - 'd' to toggle dribbler
            - 'c' to charge kicker, 'k' to kick
            Ball (IF SIMULATING):
            - Click or 'b' to select
            - Click to place (drag for speed)
            """)

        if self._mode == "entry_video":
            print("2020 Registration Video Procedure!")
            self.video_phase = 1
        if self._mode == "goalie_test":
            self._goalie_id = None
        if self._mode == "attacker_test":
            self._attacker_id = None
        if self._mode == "defender_test":
            self._defender_id = None
        if self._mode == "full_game":
            print("default strategy for playing a full game")

    def stop_controlling(self):
        """Stop the control processes by killing it."""
        # TODO: Turn this code into killing a new process.
        if self._is_controlling:
            self._is_controlling = False
            self._control_thread.join()
            self._control_thread = None

    def run_strategy(self):
        """
        Receive messages from self.data_in_q and 
        push commands to self.commands_out_q
        """
        new_gamestate = self._get_new_gamestate()
        # do stuff
        
    def control_loop(self):
        # wait until game begins (while other threads are initializing)
        self._gs.wait_until_game_begins()
        try:
            while self._is_controlling:
                # run the strategy corresponding to the given mode
                if self._mode == "UI":
                    self.UI()
                elif self._mode == "goalie_test":
                    self.goalie_test()
                elif self._mode == "attacker_test":
                    self.attacker_test()
                elif self._mode == "defender_test":
                    self.defender_test()
                elif self._mode == "entry_video":
                    self.entry_video()
                elif self._mode == "full_game":
                    self.full_game()
                else:
                    print('(unrecognized mode, doing nothing)')

                # tell all robots to refresh their speeds based on waypoints
                team_commands = self._gs.get_team_commands(self._team)
                team_commands = list(team_commands.items())
                for robot_id, robot_commands in team_commands:
                    # stop the robot if we've lost track of it
                    if self._gs.is_robot_lost(self._team, robot_id):
                        robot_commands.set_speeds(0, 0, 0)
                    else:
                        # recalculate the speed the robot should be commanded at
                        pos = self._gs.get_robot_position(self._team, robot_id)
                        robot_commands.derive_speeds(pos)

        except Exception:
            logger.exception('Unexpected Error!')
            logger.exception(traceback.format_exc())

    # follow the user-input commands through visualizer
    def UI(self):
        gs = self._gs
        if gs.user_selected_robot is not None:
            team, robot_id = gs.user_selected_robot
            if team == self._team:
                commands = gs.get_robot_commands(self._team, robot_id)
                # apply simple commands
                commands.is_charging = gs.user_charge_command
                commands.is_kicking = gs.user_kick_command
                commands.is_dribbling = gs.user_dribble_command
                # set goal pos to click location on visualization window
                if gs.user_click_position is not None:
                    x, y = gs.user_click_position
                    if gs.user_drag_vector.any():
                        # face the dragged direction
                        dx, dy = gs.user_drag_vector
                        w = np.arctan2(dy, dx)
                    else:
                        w = None
                    goal_pos = np.array([x, y, w])
                    # Use pathfinding
                    #self.move_straight(robot_id, goal_pos, is_urgent=True)
                    if is_teleport:
                        self._simulator.put_fake_robot(team, robot_id, goal_pos)
                    else:
                        self.path_find(robot_id, goal_pos)

    def click_teleport(self, team, robot_id):
        gs = self._gs
        if gs.user_click_position is not None and robot_id is not None:
            x, y = gs.user_click_position
            if gs.user_drag_vector.any():
                # face the dragged direction
                dx, dy = gs.user_drag_vector
                w = np.arctan2(dy, dx)
            else:
                w = None
            goal_pos = np.array([x, y, w])
            self._simulator.put_fake_robot(team, robot_id, goal_pos)

    def goalie_test(self):
        gs = self._gs
        if gs.user_selected_robot is not None:
            team, robot_id = gs.user_selected_robot
            if team == self._team:
                self._goalie_id = robot_id
        if self._goalie_id is not None:
            self.goalie(self._goalie_id)

    def attacker_test(self):
        gs = self._gs
        if gs.user_selected_robot is not None:
            team, robot_id = gs.user_selected_robot
            if team == self._team:
                self._attacker_id = robot_id
        if self._attacker_id is not None:
            self.attacker(self._attacker_id)
        self.click_teleport(self._team, self._attacker_id)

    def defender_test(self):
        gs = self._gs
        if gs.user_selected_robot is not None:
            team, robot_id = gs.user_selected_robot
            if team == self._team:
                self._defender_id = robot_id
        if self._defender_id is not None:
            self.defender(self._defender_id)
        self.click_teleport(self._team, self._defender_id)

    def entry_video(self):
        robot_id_0 = 0
        robot_id_1 = 8
        # where the initial pass will be received
        reception_pos = np.array([3200., 0., self.robot_face_ball(robot_id_1)])
        pass_velocity = 800
        shoot_velocity = 1200
        # reduce for real life b.c. miniature field
        # pass_velocity = 400
        # shoot_velocity = 500

        if self.video_phase >= 6:
            self.goalie(robot_id_1, is_opposite_goal=True)

        if self.video_phase == 1:
            # robot 0 gets the ball
            got_ball = self.get_ball(robot_id_0, charge_during=pass_velocity)
            # robot 1 moves to pos to receive a pass
            self.path_find(robot_id_1, reception_pos)
            # transition once robot 0 has ball (robot 1 can keep moving)
            if got_ball:
                self.video_phase += 1
                print("Moving to video phase {}".format(self.video_phase))
        elif self.video_phase == 2:
            self.path_find(robot_id_1, reception_pos)
            # robot 0 makes the pass towards reception pos
            kicked = self.prepare_and_kick(robot_id_0, reception_pos, pass_velocity)
            if kicked:
                self.video_phase += 1
                print("Moving to video phase {}".format(self.video_phase))
        elif self.video_phase == 3:
            # robot 1 receives ball
            got_ball = self.get_ball(robot_id_1, charge_during=shoot_velocity)
            if got_ball:
                self.video_phase += 1
                print("Moving to video phase {}".format(self.video_phase))
        elif self.video_phase == 4:
            # robot 1 moves to best kick pos to shoot
            goal = self._gs.get_attack_goal(self._team)
            center_of_goal = (goal[0] + goal[1]) / 2
            shot = self.prepare_and_kick(robot_id_1, center_of_goal, shoot_velocity)
            if shot:
                self.video_phase += 1
                print("Moving to video phase {}".format(self.video_phase))
        elif self.video_phase == 5:
            self.set_dribbler(robot_id_1, False)
            self.kick_ball(robot_id_1)
            self.video_phase += 1
            print("Moving to video phase {}".format(self.video_phase))
        elif self.video_phase == 6:
            # Set robot 1 to be goalie, have them go to the goal (see top of loop)
            self.video_phase += 1
            print("Moving to video phase {}".format(self.video_phase))
        elif self.video_phase == 7:
            if self._gs.get_ball_position()[0] > 3000:
                return
            # Wait for person to place a ball, then have robot 1 go to it
            got_ball = self.get_ball(robot_id_0, charge_during=shoot_velocity)
            if got_ball:
                self.video_phase += 1
                print("Moving to video phase {}".format(self.video_phase))
        elif self.video_phase == 8:
            # Robot 1 moves to best kick pos to shoot
            goal = self._gs.get_attack_goal(self._team)
            center_of_goal = (goal[0] + goal[1]) / 2
            shot = self.prepare_and_kick(robot_id_0, center_of_goal, shoot_velocity)
            if shot:
                self.video_phase += 1
                print("Moving to video phase {}".format(self.video_phase))
        elif self.video_phase == 9:
            self.set_dribbler(robot_id_0, False)
            self.kick_ball(robot_id_0)
            # Loop back to placing the ball
            self.video_phase += 1
            print("Moving to video phase {}".format(self.video_phase))
        elif self.video_phase == 10:
            if self._gs.get_ball_position()[0] > 3000:
                self.video_phase = 7
                print("Moving back to video phase {}".format(self.video_phase))
        else:
            pass

    def full_game(self):
        coach = Coach(self)
        coach.play()
