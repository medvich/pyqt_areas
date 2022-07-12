from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.uic import loadUi
import pyqtgraph as pg

from collections import namedtuple
import numpy as np
from math import sqrt
from shapely.geometry import Polygon
from shapely.ops import unary_union
import logging
import os
import csv


PATH = os.getcwd()
UI_WIDGET_FILE = 'graphWidgetForm.ui'
POSSIBLE_OPERATIONS = ['Unite', 'Intersect', 'Subtract', 'Symmetry Difference']


def extractPolyCoordinates(geom):
    if geom.type == 'Polygon':
        exteriorCoordinates = geom.exterior.coords[:]
        interiorCoordinates = []
        for interior in geom.interiors:
            interiorCoordinates += interior.coords[:]
    elif geom.type == 'MultiPolygon':
        exteriorCoordinates = []
        interiorCoordinates = []
        for part in geom:
            epc = extractPolyCoordinates(part)  # Recursive call
            exteriorCoordinates += epc['exterior']
            interiorCoordinates += epc['interiors']
    else:
        raise ValueError('Unhandled geometry type: ' + repr(geom.type))
    return {'exterior': exteriorCoordinates,
            'interiors': interiorCoordinates}


class PolyWidget(QtWidgets.QWidget):

    DEFAULT_LINE_COLOR = (255, 255, 255, 255)
    DEFAULT_LINE_WIDTH = 3
    DEFAULT_LINE_STYLE = 'Solid'
    DEFAULT_MARKER_COLOR = (100, 255, 0, 255)
    DEFAULT_MARKER_SIZE = 3
    DEFAULT_MARKER_STYLE = 's'
    DEFAULT_FILL_COLOR = (255, 255, 255, 255)

    # ~~~ Инициализация и подключение сигналов ~~~ #

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        loadUi(UI_WIDGET_FILE, self)

        # Добавим ключ, по которому будем определять, выбран ли какой-то объект в QListWidget или нет
        self.selectedFlag = True

        # Подключим вывод в консоль о произведенных действиях (при необходимости)
        self.connectLogging(True)

        # Подключим сигналы от кнопок
        self.connectSignals()

        # Инициализируем хранилище отображаемых полигонов и область отображения
        self._init_displayData()
        self._init_displayArea()

    @staticmethod
    def connectLogging(status):
        if status:
            logging.basicConfig(format="%(asctime)s :    %(levelname)s :    %(message)s", level=logging.INFO)

    def connectSignals(self):
        self.addPolyPushButton.clicked.connect(self.addPolyButtonClicked)
        self.deletePolyPushButton.clicked.connect(self.polyDeletion)        # Только если кнопка удаления активирована
        self.polyListWidget.itemChanged.connect(self.polyItemChangedEvent)
        self.polyListWidget.itemClicked.connect(self.polyItemSelectedEvent)
        self.addPolyButtonBox.accepted.connect(self.polyAccepted)           # Только если кнопка удаления активирована
        self.addPolyButtonBox.rejected.connect(self.polyRejected)           # Только если кнопка удаления активирована
        self.savePolyPushButton.clicked.connect(self.savePoly)              # Только если кнопка удаления активирована
        self.loadPolyPushButton.clicked.connect(self.loadPoly)

        # Панель кастомизации полигонов (изначально деактивирована)
        self.lineColorButtonWidget.sigColorChanged.connect(self.lineColorChanged)
        self.markerColorButtonWidget.sigColorChanged.connect(self.markerColorChanged)
        self.polyFillColorButtonWidget.sigColorChanged.connect(self.fillColorChanged)
        self.lineStyleComboBox.activated.connect(self.lineStyleChanged)
        self.markerStyleComboBox.activated.connect(self.markerStyleChanged)
        self.lineWidthSpinBox.valueChanged.connect(self.lineWidthChanged)
        self.markerSizeSpinBox.valueChanged.connect(self.markerSizeChanged)

        # Сигналы с displayArea
        self.displayArea.scene().sigMouseMoved.connect(self.dAMouseMoved)
        self.displayArea.scene().sigMouseClicked.connect(self.dAMouseClicked)

        # Панель операций с полигонами
        self.polyOperationsComboBox.activated.connect(self.operationActivated)
        self.doPolyOperationPushButton.clicked.connect(self.doOperation)

    def _init_displayData(self):
        self.key_id = 0
        self.displayData = []
        self.customPolygonStructure = namedtuple(
            "customPolygonStructure",
            ["key_id",
             "name",
             "exterior_object",
             "interior_objects",
             "linecolor",
             "linewidth",
             "linestyle",
             "markercolor",
             "markersize",
             "markerstyle",
             "fillcolor"]
        )

    def _init_displayArea(self):
        self.dAClickFlag = False

        self.vLine = pg.InfiniteLine(angle=90, movable=False)
        self.hLine = pg.InfiniteLine(angle=0, movable=False)
        self.displayArea.addItem(self.vLine, ignoreBounds=True)
        self.displayArea.addItem(self.hLine, ignoreBounds=True)

    # ~~~ Методы, работающие с элементами в polyListWidget ~~~ #

    def savePoly(self):
        currentItem = self.polyListWidget.currentItem()
        filename = currentItem.text()

        file = QtWidgets.QFileDialog.getSaveFileName(
            self, "Сохранение", "{0}\\{1}.csv".format(PATH, filename), "CSV Files (*.csv)"
        )

        index = self.findItemIndexInData(currentItem)
        exteriorHandles = []
        for handle in self.displayData[index].exterior_object.handles:
            exteriorHandles.append(
                handle['pos'] if isinstance(handle['pos'], pg.Point) else pg.Point(handle['pos'].x(), handle['pos'].y())
            )

        with open(file[0], 'w', newline='') as csvfile:
            headers = ['exterior']
            writer = csv.DictWriter(csvfile, delimiter=";", fieldnames=headers)
            writer.writeheader()
            for point in exteriorHandles:
                writer.writerow(
                    {'exterior': (point.x(), point.y())},
                )

    def loadPoly(self):
        file = QtWidgets.QFileDialog.getOpenFileName(
            self, "Открытие файла", "{0}\\*.csv".format(PATH), "CSV Files (*.csv)"
        )
        exteriorHandles = []
        with open(file[0], 'r', newline='') as csvfile:
            reader = csv.DictReader(csvfile, delimiter=";")
            for row in reader:
                exteriorHandles.append(eval(row['exterior']))

        # Создаем новый полигон по тому же принципу
        self.polyAddition(exterior=exteriorHandles)

    def polyAccepted(self):
        if len(self.tempItemsBuffer) < 3:
            QtWidgets.QMessageBox.about(self, 'Ошибка!', f'Узлов в полигоне должно быть больше 2')
            raise Exception("Polygon has too less nodes")

        # Удалим временный эскиз нового полигона
        for i in range(len(self.tempItemsBuffer)):
            self.displayArea.removeItem(self.tempItemsBuffer[i])

        self.polyAddition(exterior=self.polyBuffer)

        self.addPolyButtonBox.setEnabled(False)
        self.addPolyPushButton.setEnabled(True)
        self.dAClickFlag = False

    def polyRejected(self):
        # Удалим временный эскиз нового полигона
        for i in range(len(self.tempItemsBuffer)):
            self.displayArea.removeItem(self.tempItemsBuffer[i])

        self.addPolyButtonBox.setEnabled(False)
        self.addPolyPushButton.setEnabled(True)
        self.dAClickFlag = False

        # Информация
        logging.info(f"Отмена добавления нового элемента")
        logging.info(f"Фиксация координат кликов по displayArea выключена")

    def addPolyButtonClicked(self):
        self.addPolyButtonBox.setEnabled(True)
        self.tempItemsBuffer = []
        self.polyBuffer = []
        self.dAClickFlag = True
        self.addPolyPushButton.setEnabled(False)

        # Информация
        logging.info(f"tempBuffer очищен")
        logging.info(f"Включена фиксация координат кликов по displayArea")

    def polyDeletion(self):
        """
        Данный метод реализует удаление выбранного Item'а из QListWidget'а и из displayArea
        """

        self.selectedFlag = True

        # Определяем, какой сейчас Item selected и удаляем его из QListWidget'а
        selectedItem = self.polyListWidget.currentItem()
        self.polyListWidget.takeItem(self.polyListWidget.row(selectedItem))

        # Ищем наш полигон в displayData по key_id
        for i in range(len(self.displayData)):
            if self.displayData[i].key_id == selectedItem.data(1):
                # Сначал удаляем его с displayArea
                self.displayArea.removeItem(self.displayData[i].exterior_object)

                # Теперь удаляем его из displayArea (именно в таком порядке чтобы избежать дальнейшего ненахода)
                self.displayData.remove(self.displayData[i])

                # Информация
                logging.info(f"Ключ {selectedItem.data(1)}. Элемент {selectedItem.text()} удален")

                # Переопределяем новый выбранный элемент
                newSelectedItem = self.polyListWidget.currentItem()

                # Disabl'им кнопку удаления, кнопку addHole и меню редактирования, если ни один элемент не selected
                # (во избежания лишних тыканий и выползания ошибок)
                if newSelectedItem is None:
                    self.setItemCustomizationButtonsActive(False)
                    return

                # И снова информация, так как при удалении selected Item стал предыдущий
                logging.info(f"Ключ {newSelectedItem.data(1)}. Элемент {newSelectedItem.text()} выбран")

                # Выходим, чтобы в первую очередь прервать дальнейший поиск по циклу
                return

    def polyItemChangedEvent(self, item):
        # При изменении имени Item'а, необходимо синхронизировать эти изменения в displayData.
        # Данная функция изменяет имя полигона в displayData в соответствии с новым именем Item (возможно, это можно
        # сделать без цила, но я не нашел как...)
        polyNames = self.displayDataNames()

        for i in range(len(self.displayData)):
            if self.displayData[i].key_id == item.data(1):
                oldName = self.displayData[i].name

                # Выполним важную проверку на совпадение с уже существующими именами
                if item.text() in polyNames:
                    item.setText(oldName)
                    raise ValueError("No two names can be the same")

                # Если проверка пройдена, то изменяем имя Item'а и элемента в хранилище displayData
                self.displayData[i] = self.displayData[i]._replace(name=item.text())

                # Информация
                logging.info(f"Ключ {self.displayData[i].key_id}. Имя элемента изменено с {oldName} на {item.text()}")
                return

    def polyItemSelectedEvent(self, item):
        # Найдем selected Item в displayData
        index = self.findItemIndexInData(item)

        # Добавим возможность Select и Deselect Item
        if self._isItemSelected(item):
            item.setSelected(True)

            # self.displayData[index].exterior_object.translatable = True

            # Активируем все функции кастомизации области
            self.setItemCustomizationButtonsActive(True)
            self.fillItemCustomizationButtons(item)
            return

        # self.displayData[index].exterior_object.translatable = False
        self.setItemCustomizationButtonsActive(False)

    # ~~~ Методы, обрабатывающие сигналы от панели кастомизации полигонов ~~~ #

    def lineColorChanged(self):
        """
        Метод, меняющий цвет линий выбранного полигона
        """
        color = self.lineColorButtonWidget.color(mode='byte')

        index = self.findItemIndexInData(self.polyListWidget.currentItem())
        self.displayData[index] = \
            self.displayData[index]._replace(linecolor=color)

        # Меняем цвет линий отображаемого объекта
        self.displayData[index].exterior_object.setPen(
            pg.mkPen(color,
                     width=self.displayData[index].linewidth/3,
                     style=self.getStyleFromStr(self.displayData[index].linestyle)
                     )
        )

        # Информация
        logging.info(f"Ключ {self.displayData[index].key_id}. Цвет линий элемента {self.displayData[index].name} "
                     f"изменен на {self.displayData[index].linecolor}")

    def markerColorChanged(self):
        """
        Метод, меняющий цвет точек(узлов) выбранного полигона
        """
        color = self.markerColorButtonWidget.color(mode='byte')

        index = self.findItemIndexInData(self.polyListWidget.currentItem())
        self.displayData[index] = \
            self.displayData[index]._replace(markercolor=color)

        # Меняем цвет точек (узлов) отображаемого объекта
        for i in range(len(self.displayData[index].exterior_object.handles)):
            self.displayData[index].exterior_object.handles[i]['item'].pen.setColor(self.getColorFromTuple(color))

        # Информация
        logging.info(f"Ключ {self.displayData[index].key_id}. Цвет узлов элемента {self.displayData[index].name} "
                     f"изменен на {self.displayData[index].markercolor}")

    def fillColorChanged(self):
        """
        Метод, меняющий цвет заливки выбранного полигона
        """

        index = self.findItemIndexInData(self.polyListWidget.currentItem())
        self.displayData[index] = \
            self.displayData[index]._replace(fillcolor=self.polyFillColorButtonWidget.color(mode='byte'))

        # Информация
        logging.info(f"Ключ {self.displayData[index].key_id}. Цвет заливки элемента {self.displayData[index].name} "
                     f"изменен на {self.displayData[index].fillcolor}")

    def lineStyleChanged(self):
        """
        Метод, изменяющий стиль линий в зависимости от выбранного элемента в lineStyleComboBox
        """
        style = self.lineStyleComboBox.currentText()

        index = self.findItemIndexInData(self.polyListWidget.currentItem())
        self.displayData[index] = \
            self.displayData[index]._replace(linestyle=style)

        # Меняем стиль линий отображаемого объекта
        self.displayData[index].exterior_object.setPen(
            pg.mkPen(self.displayData[index].linecolor,
                     width=self.displayData[index].linewidth/3,
                     style=self.getStyleFromStr(style)
                     )
        )

        # Информация
        logging.info(f"Ключ {self.displayData[index].key_id}. Стиль линий элемента {self.displayData[index].name} "
                     f"изменен на {self.displayData[index].linestyle}")

    def markerStyleChanged(self):
        """
        Метод, изменяющий стиль точек (узлов) в зависимости от выбранного элемента в markerStyleComboBox
        """

        index = self.findItemIndexInData(self.polyListWidget.currentItem())
        self.displayData[index] = \
            self.displayData[index]._replace(markerstyle=self.markerStyleComboBox.currentText())

        # Информация
        logging.info(f"Ключ {self.displayData[index].key_id}. Стиль узлов элемента {self.displayData[index].name} "
                     f"изменен на {self.displayData[index].markerstyle}")

    def lineWidthChanged(self):
        """
        Метод, изменяющий толщину линий в зависимости от числа в lineWidthSpinBox
        """
        width = self.lineWidthSpinBox.value()

        index = self.findItemIndexInData(self.polyListWidget.currentItem())
        self.displayData[index] = \
            self.displayData[index]._replace(linewidth=width)

        # Меняем стиль линий отображаемого объекта
        self.displayData[index].exterior_object.setPen(
            pg.mkPen(self.displayData[index].linecolor,
                     width=width/3,
                     style=self.getStyleFromStr(self.displayData[index].linestyle)
                     )
        )

        # Информация
        logging.info(f"Ключ {self.displayData[index].key_id}. Толщина линий элемента {self.displayData[index].name} "
                     f"изменена на {self.displayData[index].linewidth}")

    def markerSizeChanged(self):
        """
        Метод, изменяющий размер точек (узлов) в зависимости от числа в markerSizeSpinBox
        """
        size = self.markerSizeSpinBox.value()

        index = self.findItemIndexInData(self.polyListWidget.currentItem())
        self.displayData[index] = \
            self.displayData[index]._replace(markersize=size)

        # Меняем размер точек (узлов) отображаемого объекта
        for i in range(len(self.displayData[index].exterior_object.handles)):
            self.displayData[index].exterior_object.handles[i]['item'].pen.setWidth(size)

        # Информация
        logging.info(f"Ключ {self.displayData[index].key_id}. Размер узлов элемента {self.displayData[index].name} "
                     f"изменен на {self.displayData[index].markersize}")

    def regionChangeFinished(self, *args):
        roi, = args

        index = None
        for i in range(len(self.displayData)):
            if self.displayData[i].exterior_object == roi:
                index = i
        if index is None:
            raise Exception("???")

        # Информация
        logging.info(f"Элемент {self.displayData[index].name} изменен")

        # Меняем цвет точек (узлов) отображаемого объекта
        for i in range(len(roi.handles)):
            roi.handles[i]['item'].pen.setColor(self.getColorFromTuple(self.markerColorButtonWidget.color(mode='byte')))
            roi.handles[i]['item'].pen.setWidth(self.markerSizeSpinBox.value())

        handles = []
        for handle in roi.handles:
            handles.append(
                handle['pos'] if isinstance(handle['pos'], pg.Point) else pg.Point(handle['pos'].x(), handle['pos'].y())
            )

        polygon = Polygon(handles)
        if not polygon.is_valid:
            print("Polygon is invalid")

    @staticmethod
    def regionChangeStarted(*args):
        roi, = args
        # roi.setState(roi.lastState)

    def regionChanged(self, *args):
        roi, = args

        index = None
        for i in range(len(self.displayData)):
            if self.displayData[i].exterior_object == roi:
                index = i
        if index is None:
            raise Exception("???")

        # Информация
        logging.info(f"Элемент {self.displayData[index].name} изменен")

        # Меняем цвет точек (узлов) отображаемого объекта
        for i in range(len(roi.handles)):
            roi.handles[i]['item'].pen.setColor(self.getColorFromTuple(self.markerColorButtonWidget.color(mode='byte')))
            roi.handles[i]['item'].pen.setWidth(self.markerSizeSpinBox.value())

    # ~~~ Методы, работающие с displayArea ~~~ #

    def dAMouseMoved(self, event):
        vb = self.displayArea.plotItem.vb
        if self.displayArea.sceneBoundingRect().contains(event):
            mousePoint = vb.mapSceneToView(event)
            self.vLine.setPos(mousePoint.x())
            self.hLine.setPos(mousePoint.y())

    def dAMouseClicked(self, event):
        if not self.dAClickFlag:
            return

        vb = self.displayArea.plotItem.vb
        sceneCoordinates = event.scenePos()

        if self.displayArea.sceneBoundingRect().contains(sceneCoordinates) and event.button() == 1:
            mousePoint = vb.mapSceneToView(sceneCoordinates)

            # Информация
            logging.info(f"Точка с координатами ({round(mousePoint.x(), 2)}, {round(mousePoint.y(), 2)}) "
                         f"добавлена в tempBuffer")

            self.polyBuffer.append((mousePoint.x(), mousePoint.y()))
            ind = -1 if len(self.polyBuffer) == 1 else -2
            x = [self.polyBuffer[ind][0], self.polyBuffer[-1][0]]
            y = [self.polyBuffer[ind][1], self.polyBuffer[-1][1]]
            tempItemObject = self.displayArea.plot(
                x, y,
                pen=pg.mkPen('w', width=0.8),
                symbol='s',
                symbolPen=(150, 255, 255, 200),
                symbolSize=7,
                symbolBrush=(0, 0, 0, 0)
            )
            self.tempItemsBuffer.append(tempItemObject)
            return

    # ~~~ Сопутствующие методы ~~~ #

    def displayDataNames(self):
        """
        Возвращает имена полигонов из displayData
        """

        res = []
        for poly in self.displayData:
            res.append(poly.name)
        return res

    def _isItemSelected(self, item):
        """
        Метод проверяет, Selected ли Item
        """
        if item.isSelected() and self.selectedFlag:
            self.selectedFlag = False
            # Информация
            logging.info(f"Ключ {item.data(1)}. Элемент {item.text()} выбран")
            return True

        item.setSelected(False)
        self.selectedFlag = True
        # Информация
        logging.info(f"Ключ {item.data(1)}. Выбор с элемента {item.text()} снят")
        return False

    def setItemCustomizationButtonsActive(self, status):
        self.savePolyPushButton.setEnabled(status)

        # Активируем/деактивируем кнопку удаления полигона
        self.deletePolyPushButton.setEnabled(status)

        # Активируем/деактивируем кнопку добавления выреза
        self.addHolePushButton.setEnabled(status)

        # Активируем/деактивируем меню редактирования
        self.lineColorButtonWidget.setEnabled(status)
        self.markerColorButtonWidget.setEnabled(status)
        # self.polyFillColorButtonWidget.setEnabled(status)     # Заливка
        self.lineStyleComboBox.setEnabled(status)
        self.markerStyleComboBox.setEnabled(status)
        self.lineWidthSpinBox.setEnabled(status)
        self.markerSizeSpinBox.setEnabled(status)

    def fillItemCustomizationButtons(self, item):
        # Найдем selected Item в displayData
        index = self.findItemIndexInData(item)
        selectedItemFromData = self.displayData[index] if index is not None else None

        # Если нашли (что хотелось бы...), то заполняем панель кастомизации, исходя из информации о полигоне
        # в displayData
        if selectedItemFromData is not None:
            self.lineColorButtonWidget.setColor(selectedItemFromData.linecolor)
            self.markerColorButtonWidget.setColor(selectedItemFromData.markercolor)
            # self.polyFillColorButtonWidget.setColor(selectedItemFromData.fillcolor)     # Заливка

            assert selectedItemFromData.linestyle in \
                   [self.lineStyleComboBox.itemText(i) for i in
                    range(self.lineStyleComboBox.count())], "Default linestyle not in possible linestyle list"
            self.lineStyleComboBox.setCurrentText(selectedItemFromData.linestyle)

            assert selectedItemFromData.markerstyle in \
                   [self.markerStyleComboBox.itemText(i) for i in
                    range(self.markerStyleComboBox.count())], "Default markerstyle not in possible markerstyle list"
            self.markerStyleComboBox.setCurrentText(selectedItemFromData.markerstyle)

            self.lineWidthSpinBox.setValue(selectedItemFromData.linewidth)
            self.markerSizeSpinBox.setValue(selectedItemFromData.markersize)
        else:
            raise Exception("Couldn't find selected item in displayData...")

    def findItemIndexInData(self, item):
        """
        Метод ищет индекс Item'а в displayData и возвращает его или None,
        если элемент не нашелся (надеюсь, такого не будет)
        """

        for i in range(len(self.displayData)):
            if self.displayData[i].key_id == item.data(1):
                return i
        return None

    def getDisplayAreaState(self):
        return self.displayArea.getViewBox().state['viewRange']

    @staticmethod
    def getSimplePolygon(displayAreaState, bias=0):
        """
        Метод возвращает координаты самого простого полигона (треугольника) с ЦМ в центре displayArea длиной
        сторон, зависящей от текущего состояния displayArea
        """

        areaLength = abs(displayAreaState[0][1] - displayAreaState[0][0])
        areaHeight = abs(displayAreaState[1][1] - displayAreaState[1][0])

        mid = np.array([
            displayAreaState[0][0] + areaLength / 2,
            displayAreaState[1][0] + areaHeight / 2
        ]) + bias
        r = areaLength / 15

        return [
            mid + np.array([-r * sqrt(3/2), -r * 0.5]),
            mid + np.array([0, r]),
            mid + np.array([r * sqrt(3/2), -r * 0.5])
        ]

    @staticmethod
    def getStyleFromStr(string):
        if string.lower() == "solid":
            return QtCore.Qt.SolidLine
        elif string.lower() == "dashed":
            return QtCore.Qt.DashLine
        if string.lower() == "dash-dotted":
            return QtCore.Qt.DashDotLine
        return QtCore.Qt.DotLine

    @staticmethod
    def getColorFromTuple(tup):
        if len(tup) > 3:
            return QtGui.QColor(tup[0], tup[1], tup[2], tup[3])
        return QtGui.QColor(tup[0], tup[1], tup[2])

    # ~~~ Операции с полигонами ~~~ #

    def doOperation(self):
        operation = self.polyOperationsComboBox.currentText()

        polyName1 = self.poly1LineEdit.text()
        index1 = None
        for i in range(len(self.displayData)):
            if self.displayData[i].name == polyName1:
                index1 = i
        if index1 is None:
            QtWidgets.QMessageBox.about(self, 'Ошибка!', f'Области с именем {polyName1} не существует')
            return

        polyName2 = self.poly2LineEdit.text()
        index2 = None
        for i in range(len(self.displayData)):
            if self.displayData[i].name == polyName2:
                index2 = i
        if index2 is None:
            QtWidgets.QMessageBox.about(self, 'Ошибка!', f'Области с именем {polyName2} не существует')
            return

        roi1 = self.displayData[index1].exterior_object
        roi2 = self.displayData[index2].exterior_object

        handles1 = []
        for handle in roi1.handles:
            handles1.append(
                handle['pos'] if isinstance(handle['pos'], pg.Point) else pg.Point(handle['pos'].x(), handle['pos'].y())
            )

        handles2 = []
        for handle in roi2.handles:
            handles2.append(
                handle['pos'] if isinstance(handle['pos'], pg.Point) else pg.Point(handle['pos'].x(), handle['pos'].y())
            )

        polygon1 = Polygon(handles1)
        polygon2 = Polygon(handles2)

        if operation == "Unite":
            union = unary_union((polygon1, polygon2))
            unionCoordinates = extractPolyCoordinates(union)

            itemsInListWidget = [self.polyListWidget.item(x) for x in range(self.polyListWidget.count())]

            for item in itemsInListWidget:
                if item.text() == polyName1:
                    item.setSelected(True)
                    self.polyDeletion()

            for item in itemsInListWidget:
                if item.text() == polyName2:
                    item.setSelected(True)
                    self.polyDeletion()

            self.polyAddition(exterior=unionCoordinates['exterior'])

        if operation == "Intersect":
            intersection = polygon1.intersection(polygon2)
            intersectionCoordinates = extractPolyCoordinates(intersection)

            itemsInListWidget = [self.polyListWidget.item(x) for x in range(self.polyListWidget.count())]

            for item in itemsInListWidget:
                if item.text() == polyName1:
                    item.setSelected(True)
                    self.polyDeletion()

            for item in itemsInListWidget:
                if item.text() == polyName2:
                    item.setSelected(True)
                    self.polyDeletion()

            self.polyAddition(exterior=intersectionCoordinates['exterior'])

        if operation == "Subtract":
            subtraction = polygon1.difference(polygon2)
            subtractionCoordinates = extractPolyCoordinates(subtraction)

            itemsInListWidget = [self.polyListWidget.item(x) for x in range(self.polyListWidget.count())]

            # [pg.Point(x, y) for (x, y) in subtractionCoordinates['exterior']]

            for item in itemsInListWidget:
                if item.text() == polyName1:
                    item.setSelected(True)
                    self.polyDeletion()

            self.polyAddition(exterior=subtractionCoordinates['exterior'])

        if operation == "Symmetry Difference":
            difference1 = polygon1.difference(polygon2)
            difference2 = polygon2.difference(polygon1)

            difference1Coordinates = extractPolyCoordinates(difference1)
            difference2Coordinates = extractPolyCoordinates(difference2)

            itemsInListWidget = [self.polyListWidget.item(x) for x in range(self.polyListWidget.count())]

            for item in itemsInListWidget:
                if item.text() == polyName1:
                    item.setSelected(True)
                    self.polyDeletion()

            for item in itemsInListWidget:
                if item.text() == polyName2:
                    item.setSelected(True)
                    self.polyDeletion()

            self.polyAddition(exterior=difference1Coordinates['exterior'])
            self.polyAddition(exterior=difference2Coordinates['exterior'])

        self.poly1LineEdit.clear()
        self.poly2LineEdit.clear()

    def operationActivated(self):
        operation = self.polyOperationsComboBox.currentText()

        if operation not in POSSIBLE_OPERATIONS:
            QtWidgets.QMessageBox.about(self, 'Ошибка!', f'Такая операция не поддерживается')
            raise Exception("Impossible operation")

    @staticmethod
    def get2PolyUnion(poly1, poly2):
        pass

    @staticmethod
    def convertROI2Polygon(obj, reverse=False):
        pass

    #...

    def polyAddition(self, exterior=None):
        assert exterior is not None, "Need to add exterior coordinates"

        # Преобразуем новый полигон в Item, чтобы можно было с ним работать, как с QListWidgetItem
        newPolygonAsItem = QtWidgets.QListWidgetItem(self.polyListWidget)
        polyNames = self.displayDataNames()

        # Пресечем возможность совпадения имен при добавлении нового элемента
        newPolyName = f"Polygon_{self.key_id + 1}"
        newPolygonAsItem.setText(newPolyName if newPolyName not in polyNames else f"Polygon_{self.key_id + 2}")
        newPolygonAsItem.setData(1, self.key_id)

        # Добавляем Item на наш QListWidget и присваиваем ему дефолтное имя по порядку, исходя из displayData.
        self.polyListWidget.addItem(newPolygonAsItem)

        # Сделаем поле с названием полигона изменяемым (удобно ж). Но надо не забыть учесть изменение имя пользователем
        # в хранилище displayData
        newPolygonAsItem.setFlags(newPolygonAsItem.flags() | QtCore.Qt.ItemIsEditable)

        # Создадим на его месте полноценное изображение полигона
        exteriorObj = pg.PolyLineROI(
            exterior,
            closed=True,
            movable=True,
            pen=pg.mkPen(self.DEFAULT_LINE_COLOR,
                         width=self.DEFAULT_LINE_WIDTH/3,
                         style=self.getStyleFromStr(self.DEFAULT_LINE_STYLE)),
            handlePen=pg.mkPen(self.DEFAULT_MARKER_COLOR)
        )
        for handle in exteriorObj.handles:
            handle['item'].pen.setWidth(self.DEFAULT_MARKER_SIZE)
        self.displayArea.addItem(exteriorObj)

        exteriorObj.sigRegionChangeStarted.connect(self.regionChangeStarted)
        # exteriorObj.sigRegionChanged.connect(self.regionChanged)
        exteriorObj.sigRegionChangeFinished.connect(self.regionChangeFinished)

        # Создаем новый полигон как объект структуры customPolygonStructure
        newPolygon = self.customPolygonStructure(
            newPolygonAsItem.data(1),
            newPolygonAsItem.text(),
            exteriorObj,
            [],
            self.DEFAULT_LINE_COLOR,
            self.DEFAULT_LINE_WIDTH,
            self.DEFAULT_LINE_STYLE,
            self.DEFAULT_MARKER_COLOR,
            self.DEFAULT_MARKER_SIZE,
            self.DEFAULT_MARKER_STYLE,
            self.DEFAULT_FILL_COLOR
        )

        # Добавляем Item в хранилище отображаемых полигонов
        self.displayData.append(newPolygon)

        # Увеличиваем key_id для следующего полигона
        self.key_id += 1

        # Информация
        logging.info(f"Добавлен новый элемент {newPolygon.name} с ключом {newPolygon.key_id}")
