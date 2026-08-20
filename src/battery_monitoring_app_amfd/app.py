import time

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import (
    QObject,
    Qt,
    QThread,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from serial import Serial, SerialException
from serial.tools import list_ports


class ThreadReadSerial(QThread):
    """
    Worker thread that reads from the serial port and sends the data
    to the GUI thread
    """

    # why are signals in the book as class attributes and not
    # instance attributes?
    data = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, com_port):
        super().__init__()
        self.com_port = com_port

        self.stop = False

    def stop_execution(self):
        self.stop = True

    @pyqtSlot()
    def run(self):
        print("[ReadSerial] started")
        lines_read = []
        try:
            with Serial(self.com_port, 115200) as ser:
                try:
                    while True:
                        while ser.in_waiting:
                            line = ser.readline()
                            lines_read.append(line)

                        # send data read and saved so far, if any
                        if lines_read:
                            self.data.emit(lines_read)
                            lines_read = []

                        # terminate
                        if self.stop:
                            print("[ReadSerial] stopping...")
                            break

                        # if not terminated, pause before reading data again
                        time.sleep(0.1)

                except SerialException as se:
                    print(se)
                    error_msg = (
                        se.args[0].split(',')[1].replace('\'', '').strip()
                    )
                    print(error_msg)
                    recognized_error_msgs = (
                        # disconnected during operation
                        'The device does not recognize the command.',
                    )
                    if error_msg not in recognized_error_msgs:
                        self.error.emit(
                            f"Could not read from serial port: {se}"
                        )
                        raise se

                    self.error.emit(
                        f"Could not read from serial port: {error_msg}"
                    )

        except SerialException as se:
            print(se)
            error_msg = se.args[0].split(',')[1].replace('\'', '').strip()
            print(error_msg)
            recognized_error_msgs = (
                # port busy (e.g., open somewhere else)
                'Access is denied.',
                # invalid (bugged?) port
                'The semaphore timeout period has expired.',
                # invalid (inexistent) port
                'The system cannot find the file specified.',
            )
            if error_msg not in recognized_error_msgs:
                self.error.emit(f"Could not open serial port: {se}")
                raise se

            self.error.emit(f"Could not open serial port: {error_msg}")

        print("[ReadSerial] stopped")


class ThreadProcessSerial(QThread):
    """
    Worker thread that receives the readings from the serial port
    processes them for plotting and statistics calculation
    """

    data = pyqtSignal(dict)
    plot = pyqtSignal(int)
    calc_stats = pyqtSignal(int)

    def __init__(
            self, data_len, t, history_data, plotted_data, iteration_time,
            plot_names, pens
    ):
        super().__init__()
        self.data_len = data_len
        self.t = t
        self.history_data = history_data
        self.plotted_data = plotted_data
        self.iteration_time = iteration_time
        self.plot_names = plot_names
        self.pens = pens

        self.received_data = []

        self.stop = False

    def stop_execution(self):
        self.stop = True

    def receive_data(self, data):
        self.received_data.append(data)

    @pyqtSlot()
    def run(self):
        print("[ProcessSerial] started")
        decoding_errors_cnt = 0
        incomplete_lines_cnt = 0
        data_processed = {}
        while True:
            # process all received data so far
            while self.received_data:
                data = self.received_data[0]
                del self.received_data[0]

                for line_read in data:
                    # process data
                    try:
                        line_decoded = line_read.decode('ASCII')
                    except UnicodeDecodeError:
                        # sometimes the first bytes of
                        # line read causes error while
                        # decoding (garbage bytes)
                        print('[ProcessSerial] Decode error')

                        decoding_errors_cnt += 1
                        if decoding_errors_cnt > 1:
                            raise Exception

                        continue

                    if (
                        not line_decoded.startswith('1:')
                        and not line_decoded.startswith('T:')
                    ):
                        # the line sent by the MCU was only partially
                        # received or it is a line not concerning
                        # sensor data (e.g., MCU initialization, timings)
                        print('[ProcessSerial] Incomplete line')
                        # TODO: must only start counting incomplete lines
                        # after first valid line read

                        incomplete_lines_cnt += 1
                        if incomplete_lines_cnt > 10:
                            raise Exception

                        continue

                    split_res = line_decoded.split(';')
                    if len(split_res) == 4:
                        # 3-channel data plus carriage return and newline
                        # read first channel data completely
                        for i in range(3):
                            ch_vals = split_res[i].split(':')

                            if ch_vals[0] == str(i+1):
                                if ch_vals[0] not in data_processed:
                                    data_processed[ch_vals[0]] = {}
                                    data_processed[ch_vals[0]]['vol'] = []
                                    data_processed[ch_vals[0]]['cur'] = []

                                vol_cur = ch_vals[1].split(',')
                                (
                                    data_processed[ch_vals[0]]['vol']
                                    .append(int(vol_cur[0]))
                                )
                                (
                                    data_processed[ch_vals[0]]['cur']
                                    .append(int(vol_cur[1]))
                                )

            # if there is valid processed received data, process it further
            # for plotting
            if data_processed:
                tmp_vol1 = np.array(data_processed['1']['vol'])
                tmp_vol2 = np.array(data_processed['2']['vol'])
                tmp_vol3 = np.array(data_processed['3']['vol'])

                tmp_cur1 = np.array(data_processed['1']['cur'])
                tmp_cur2 = np.array(data_processed['2']['cur'])
                tmp_cur3 = np.array(data_processed['3']['cur'])

                plotted_data_aux = [
                    [[] for row in range(2)] for col in range(3)
                ]

                # computed voltages
                plotted_data_aux[0][0] = [
                    tmp_vol2, tmp_vol3  # battery, charger
                ]
                plotted_data_aux[1][0] = [
                    tmp_vol1, tmp_vol2 - tmp_vol1  # cell arrays
                ]
                plotted_data_aux[2][0] = [
                    tmp_vol2 - 2*tmp_vol1  # cell difference
                ]

                # computed currents
                plotted_data_aux[0][1] = [tmp_cur3]  # charge
                plotted_data_aux[1][1] = [tmp_cur2]  # discharge
                plotted_data_aux[2][1] = [tmp_cur1]  # equalizer
                if not self.history_data:
                    # first batch of received data
                    self.t.append(
                        np.arange(1, len(data_processed['1']['vol'])+1)
                        * self.iteration_time
                    )
                    for ch in range(3):
                        self.history_data[str(ch+1)] = {}
                        self.history_data[str(ch+1)]['vol'] = (
                            data_processed[str(ch+1)]['vol']
                        )
                        self.history_data[str(ch+1)]['cur'] = (
                            data_processed[str(ch+1)]['cur']
                        )

                    for i in range(3):
                        for vol_cur in range(2):
                            for p in range(len(plotted_data_aux[i][vol_cur])):
                                self.plotted_data[i][vol_cur].append(
                                    plotted_data_aux[i][vol_cur][p]
                                )
                else:
                    # concatenate batch data with
                    # previously received data
                    self.t[0] = np.concatenate(
                        (
                            self.t[0],
                            self.t[0][-1]
                            + np.arange(1, len(data_processed['1']['vol'])+1)
                            * self.iteration_time,
                        ),
                    )
                    for ch in range(3):
                        (
                            self.history_data[str(ch+1)]['vol']
                            .extend(data_processed[str(ch+1)]['vol'])
                        )
                        (
                            self.history_data[str(ch+1)]['cur']
                            .extend(data_processed[str(ch+1)]['cur'])
                        )

                    for i in range(3):
                        for vol_cur in range(2):
                            for p in range(len(self.plotted_data[i][vol_cur])):
                                self.plotted_data[i][vol_cur][p] = (
                                    np.concatenate(
                                        (
                                            self.plotted_data[i][vol_cur][p],
                                            plotted_data_aux[i][vol_cur][p],
                                        )
                                    )
                                )

                self.data_len[0] += len(data_processed['1']['vol'])
                data_processed = {}
                self.plot.emit(self.data_len[0])
                self.calc_stats.emit(self.data_len[0])

            if self.stop:
                print("[ProcessSerial] stopping...")
                break

            time.sleep(0.1)

        print("[ProcessSerial] stopped")


class CalcStatsSignal(QObject):
    signal = pyqtSignal(str)

    def emit(self, data):
        self.signal.emit(data)


class ThreadCalcStats(QThread):
    """
    Worker thread that calculates plotted data statistics and emits signals
    for the GUI thread to update label widgets
    """

    def __init__(self, stats_names, plotted_data, layout_stats_vals):
        super().__init__()
        self.stats_names = stats_names
        self.plotted_data = plotted_data
        self.layout_stats_vals = layout_stats_vals
        self.data_len = None

        self.stop = False

        # helper references
        self.items = [self.layout_stats_vals.itemAt(j) for j in range(1, 4+1)]

        # connect signals to slots (thread-safe execution)
        self.label_signals = []
        idx = 0
        for i in range(3):
            for vol_cur in range(2):
                for p in range(len(self.stats_names[i][vol_cur])):
                    self.label_signals.append([])
                    for j in range(4):
                        self.label_signals[idx].append(CalcStatsSignal())
                        self.label_signals[idx][j].signal.connect(
                            self.items[j].itemAt(idx).widget().setText
                        )

                    idx += 1

    def stop_execution(self):
        self.stop = True

    def receive_data(self, data_len):
        self.data_len = data_len

    @pyqtSlot()
    def run(self):
        print("[CalcStats] started")
        while True:
            if self.data_len is None:
                time.sleep(0.1)

                continue
            data_len = self.data_len
            self.data_len = None

            idx = 0
            for i in range(3):
                for vol_cur in range(2):
                    for p in range(len(self.plotted_data[i][vol_cur])):

                        mean = np.mean(
                            self.plotted_data[i][vol_cur][p]
                            [:data_len]
                        )
                        max_ = np.max(
                            self.plotted_data[i][vol_cur][p]
                            [:data_len]
                        )
                        min_ = np.min(
                            self.plotted_data[i][vol_cur][p]
                            [:data_len]
                        )

                        self.label_signals[idx][0].emit(
                            str(self.plotted_data[i][vol_cur][p][-1])
                        )
                        self.label_signals[idx][1].emit(str(round(mean)))
                        self.label_signals[idx][2].emit(str(round(max_)))
                        self.label_signals[idx][3].emit(str(round(min_)))

                        idx += 1

            if self.stop:
                print("[CalcStats] stopping...")
                break

            time.sleep(0.1)

        print("[CalcStats] stopped")


class BatMonUI(QMainWindow):

    def __init__(self):
        super().__init__()

        self.data_len = None
        self.t = None
        self.history_data = None
        self.plotted_data = None
        self.lines = None
        self.pens = ['y', 'b']
        self.plot_names = [[None, None], [['V1', 'V2'], None], [None, None]]

        layout = QHBoxLayout()
        layout_right = QVBoxLayout()
        self.graphWidget = pg.GraphicsLayoutWidget()
        self.plot_titles = [
            ['battery, charger', 'charge'],  # plots 1st column
            ['cell arrays', 'discharge'],  # plots 2nd column
            ['cell diff', 'equalizer'],  # plots 3rd column
        ]
        self.plots = [[None for row in range(2)] for col in range(3)]
        for i in range(3):
            for vol_cur in range(2):
                self.plots[i][vol_cur] = self.graphWidget.addPlot(
                    row=vol_cur, col=i,
                    title=self.plot_titles[i][vol_cur],
                )

                if vol_cur == 1:
                    self.plots[i][vol_cur].setLabel("bottom", "t (s)")

            if i == 0:
                if vol_cur == 0:
                    self.plots[i][vol_cur].setLabel("left", "voltage (mV)")
                else:
                    self.plots[i][vol_cur].setLabel("left", "current (mA)")
        self.iteration_time = 5e-3

        layout.addWidget(self.graphWidget)

        labelSerialPortTxt = QLabel()
        labelSerialPortTxt.setStyleSheet('font-weight: bold')
        labelSerialPortTxt.setText('Port:')
        labelSerialPortTxt.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.port_list = QComboBox()
        self.port_list.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed
        )

        layout_serial_port = QHBoxLayout()
        layout_serial_port.addWidget(labelSerialPortTxt)
        layout_serial_port.addWidget(self.port_list)

        self.button_list_ports = QPushButton("Refresh port list")
        self.button_list_ports.pressed.connect(self.list_com_ports)

        self.button_reading = QPushButton("Start reading")
        self.button_reading.pressed.connect(self.start_reading)

        self.stats_names = [
            [['Vbat', 'Vchg'], ['Ichg']],
            [['V1', 'V2'], ['Iload']],
            [['Vdiff'], ['Ieq']],
        ]

        layout_stats_names = QVBoxLayout()
        layout_stats_curs = QVBoxLayout()
        layout_stats_avgs = QVBoxLayout()
        layout_stats_maxs = QVBoxLayout()
        layout_stats_mins = QVBoxLayout()
        layouts_stats = [
            layout_stats_names,
            layout_stats_curs,
            layout_stats_avgs,
            layout_stats_maxs,
            layout_stats_mins,
        ]
        for i in range(3):
            for vol_cur in range(2):
                for p in range(len(self.stats_names[i][vol_cur])):
                    layout_stats_names.addWidget(
                        QLabel(self.stats_names[i][vol_cur][p] + ': ')
                    )
                    layout_stats_curs.addWidget(QLabel("curr"))
                    layout_stats_avgs.addWidget(QLabel("avg"))
                    layout_stats_maxs.addWidget(QLabel("max"))
                    layout_stats_mins.addWidget(QLabel("min"))

        self.layout_stats_vals = QHBoxLayout()
        for layout_stats in layouts_stats:
            layout_stats.setAlignment(Qt.AlignmentFlag.AlignTop)
            self.layout_stats_vals.addLayout(layout_stats)

        self.error_dialog = QMessageBox(
            QMessageBox.Icon.Warning, 'Warning', ''
        )
        self.error_msg_serial_unavailable = (
            'No available COM port.\nClick the button to update port list and'
            ' select an available COM port.'
        )
        self.error_msg_serial_reading = ''

        layout_right_components = [
            layout_serial_port,
            self.button_list_ports,
            self.button_reading,
            QLabel("Statistics (curr, avg, max, min):"),
        ]
        for comp in layout_right_components:
            if isinstance(comp, QWidget):
                layout_right.addWidget(comp)
            elif isinstance(comp, QBoxLayout):
                layout_right.addLayout(comp)

        layout_right.addLayout(self.layout_stats_vals)
        layout_right.setAlignment(Qt.AlignmentFlag.AlignTop)

        w_right = QWidget()
        w_right.setLayout(layout_right)

        layout.addWidget(w_right)

        w = QWidget()
        w.setLayout(layout)

        self.setCentralWidget(w)

        self.setWindowTitle('Battery Monitoring Application')
        self.list_com_ports()

        self.show()

        self.port_list.setMinimumWidth(self.port_list.width())
        self.port_list.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed
        )

    def list_com_ports(self):
        self.ports = [port.device for port in list_ports.comports()]

        self.port_list.clear()
        self.port_list.addItems(self.ports)

    def start_reading(self):
        self.button_reading.setDisabled(True)

        com_port = self.port_list.currentText()
        if not com_port:
            self.error_dialog.setText(self.error_msg_serial_unavailable)
            self.error_dialog.show()
        else:
            self.data_len = [0]
            self.t = []
            self.history_data = {}
            self.plotted_data = [[[] for row in range(2)] for col in range(3)]
            self.lines = [[[] for row in range(2)] for col in range(3)]
            for i in range(3):
                for vol_cur in range(2):
                    self.plots[i][vol_cur].clear()

            self.thread_read_serial = ThreadReadSerial(com_port)
            self.thread_process_serial = ThreadProcessSerial(
                self.data_len,
                self.t,
                self.history_data,
                self.plotted_data,
                self.iteration_time,
                self.plot_names,
                self.pens,
            )
            self.thread_calc_stats = ThreadCalcStats(
                self.stats_names,
                self.plotted_data,
                self.layout_stats_vals
            )

            self.thread_read_serial.data.connect(
                self.thread_process_serial.receive_data
            )
            self.thread_read_serial.error.connect(self.error_read_serial)
            self.thread_process_serial.plot.connect(self.plot)
            self.thread_process_serial.calc_stats.connect(
                self.thread_calc_stats.receive_data
            )

            self.thread_read_serial.start()
            self.thread_process_serial.start()
            self.thread_calc_stats.start()

            # change text to stop, change slot for the clicked signal
            self.button_reading.pressed.disconnect(self.start_reading)
            self.button_reading.pressed.connect(self.stop_reading)
            self.button_reading.setText('Stop reading')

        self.button_reading.setDisabled(False)

    def stop_reading(self):
        self.button_reading.setDisabled(True)

        self.thread_read_serial.stop_execution()
        self.thread_process_serial.stop_execution()
        self.thread_calc_stats.stop_execution()

        self.button_reading.pressed.disconnect(self.stop_reading)
        self.button_reading.pressed.connect(self.start_reading)
        self.button_reading.setText('Start reading')
        self.button_reading.setDisabled(False)

    def error_read_serial(self, msg):
        self.error_dialog.setText(msg)
        self.error_dialog.show()

        self.stop_reading()

    def plot(self, data_len_to_plot):
        empty_plots = False
        if not self.lines[0][0]:
            empty_plots = True

        for i in range(3):
            for vol_cur in range(2):
                for p in range(len(self.plotted_data[i][vol_cur])):
                    if empty_plots:
                        if self.plot_names[i][vol_cur]:
                            name = self.plot_names[i][vol_cur][p]
                        else:
                            name = None
                        self.lines[i][vol_cur].append(
                            self.plots[i][vol_cur].plot(
                                self.t[0][:data_len_to_plot],
                                self.plotted_data[i][vol_cur][p]
                                [:data_len_to_plot],
                                pen=self.pens[p],
                                name=name
                            )
                        )
                    else:
                        self.lines[i][vol_cur][p].setData(
                            self.t[0][:data_len_to_plot],
                            self.plotted_data[i][vol_cur][p][:data_len_to_plot]
                        )

                if empty_plots:
                    self.plots[i][vol_cur].addLegend()


class BatMonApp(QApplication):
    def __init__(self, args, **kwargs):
        super().__init__(args, **kwargs)

        # reference to BatMonUI/QMainWindow needs to be kept, otherwise window
        # object is destroyed shortly after creation due to garbage collection
        self.window = BatMonUI()
