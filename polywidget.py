from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.uic import loadUi
import pyqtgraph as pg

from collections import namedtuple
import numpy as np
from math import sqrt
from shapely.geometry import Polygon
from shapely.ops import unary_union
import logging


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
        self.addPolyPushButton.clicked.connect(self.polyAddition)
        self.deletePolyPushButton.clicked.connect(self.polyDeletion)    # Только если кнопка удаления активирована
        self.polyListWidget.itemChanged.connect(self.polyItemChangedEvent)
        self.polyListWidget.itemClicked.connect(self.polyItemSelectedEvent)
        self.addPolyButtonBox.accepted.connect(self.polyAccepted)      # Только если кнопка удаления активирована

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
             "exterior",
             "interiors",
             "linecolor",
             "linewidth",
             "linestyle",
             "markercolor",
             "markersize",
             "markerstyle",
             "fillcolor",
             "display_object"]
        )

    def _init_displayArea(self):
        self.dAClickFlag = False

        self.vLine = pg.InfiniteLine(angle=90, movable=False)
        self.hLine = pg.InfiniteLine(angle=0, movable=False)
        self.displayArea.addItem(self.vLine, ignoreBounds=True)
        self.displayArea.addItem(self.hLine, ignoreBounds=True)

    # ~~~ Методы, работающие с элементами в polyListWidget ~~~ #

    def polyAccepted(self):
        if len(self.tempItemsBuffer) < 3:
            QtWidgets.QMessageBox.about(self, 'Ошибка!', f'Узлов в полигоне должно быть больше 2')
            raise Exception("Polygon has too less nodes")

        # Преобразуем новый полигон в Item, чтобы можно было с ним работать, как с QListWidgetItem
        newPolygonAsItem = QtWidgets.QListWidgetItem(self.polyListWidget)

        polyNames = self.displayDataNames()

        # Пресечем возможность совпадения имен ри добавлении нового элемента
        newPolyName = f"Polygon_{self.key_id + 1}"
        newPolygonAsItem.setText(newPolyName if newPolyName not in polyNames else f"Polygon_{self.key_id + 2}")
        newPolygonAsItem.setData(1, self.key_id)

        # Добавляем Item на наш QListWidget и присваиваем ему дефолтное имя по порядку, исходя из displayData.
        self.polyListWidget.addItem(newPolygonAsItem)

        # Сделаем поле с названием полигона изменяемым (удобно ж). Но надо не забыть учесть изменение имя пользователем
        # в хранилище displayData
        newPolygonAsItem.setFlags(newPolygonAsItem.flags() | QtCore.Qt.ItemIsEditable)

        # Удалим временный эскиз нвого полигона
        for i in range(len(self.tempItemsBuffer)):
            self.displayArea.removeItem(self.tempItemsBuffer[i])

        # Создадим на его месте полноценное изображение полигона
        p = pg.PolyLineROI(
            self.polyBuffer,
            closed=True,
            movable=True,
            pen=pg.mkPen(self.DEFAULT_LINE_COLOR,
                         width=self.DEFAULT_LINE_WIDTH/3,
                         style=self.getStyleFromStr(self.DEFAULT_LINE_STYLE)),
            handlePen=pg.mkPen(self.DEFAULT_MARKER_COLOR)
        )
        for handle in p.handles:
            handle['item'].pen.setWidth(self.DEFAULT_MARKER_SIZE)
        self.displayArea.addItem(p)

        # p.sigRegionChangeStarted.connect(self.polyChangeStarted)
        p.sigRegionChanged.connect(self.regionChanged)

        # Создаем новый полигон как объект структуры customPolygonStructure
        newPolygon = self.customPolygonStructure(
            newPolygonAsItem.data(1),
            newPolygonAsItem.text(),
            self.polyBuffer,
            [],
            self.DEFAULT_LINE_COLOR,
            self.DEFAULT_LINE_WIDTH,
            self.DEFAULT_LINE_STYLE,
            self.DEFAULT_MARKER_COLOR,
            self.DEFAULT_MARKER_SIZE,
            self.DEFAULT_MARKER_STYLE,
            self.DEFAULT_FILL_COLOR,
            p
        )
        assert type(newPolygon.name) is str and \
               type(newPolygon.exterior) in (list, np.ndarray) and \
               type(newPolygon.interiors) in (list, np.ndarray), "Wrong parameter or parameters type"

        # Добавляем Item в хранилище отображаемых полигонов
        self.displayData.append(newPolygon)

        # Увеличиваем key_id для следующего полигона
        self.key_id += 1

        # Информация
        logging.info(f"Добавлен новый элемент {newPolygon.name} с ключом {newPolygon.key_id}")

        self.addPolyButtonBox.setEnabled(False)
        self.addPolyPushButton.setEnabled(True)
        self.dAClickFlag = False

    def polyAddition(self):
        self.addPolyButtonBox.setEnabled(True)

        self.tempItemsBuffer = []
        self.polyBuffer = []

        logging.info(f"tempBuffer очищен")

        self.dAClickFlag = True
        self.addPolyPushButton.setEnabled(False)

        # Информация
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
                self.displayArea.removeItem(self.displayData[i].display_object)

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

            # self.displayData[index].display_object.translatable = True

            # Активируем все функции кастомизации области
            self.setItemCustomizationButtonsActive(True)
            self.fillItemCustomizationButtons(item)
            return

        # self.displayData[index].display_object.translatable = False
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
        self.displayData[index].display_object.setPen(
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
        for i in range(len(self.displayData[index].display_object.handles)):
            self.displayData[index].display_object.handles[i]['item'].pen.setColor(self.getColorFromTuple(color))

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
        self.displayData[index].display_object.setPen(
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
        self.displayData[index].display_object.setPen(
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
        for i in range(len(self.displayData[index].display_object.handles)):
            self.displayData[index].display_object.handles[i]['item'].pen.setWidth(size)

        # Информация
        logging.info(f"Ключ {self.displayData[index].key_id}. Размер узлов элемента {self.displayData[index].name} "
                     f"изменен на {self.displayData[index].markersize}")

    # @staticmethod
    # def polyChangeStarted(*args):
    #     roi, = args
    #     roi.setState(roi.lastState)
    #

    def regionChanged(self, *args):
        roi, = args

        index = None
        for i in range(len(self.displayData)):
            if self.displayData[i].display_object == roi:
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

        if operation == "Unite":
            roi1 = self.displayData[index1].display_object
            roi2 = self.displayData[index2].display_object

            polygon1 = Polygon([handle['pos'] for handle in roi1.handles])
            polygon2 = Polygon([handle['pos'] for handle in roi2.handles])

            union = unary_union((polygon1, polygon2))
            unionCoordinates = extractPolyCoordinates(union)

            newItem = pg.PolyLineROI(
                unionCoordinates['exterior'],
                closed=True,
                movable=True,
                pen=pg.mkPen(self.DEFAULT_LINE_COLOR,
                             width=self.DEFAULT_LINE_WIDTH / 3,
                             style=self.getStyleFromStr(self.DEFAULT_LINE_STYLE)),
                handlePen=pg.mkPen(self.DEFAULT_MARKER_COLOR)
            )
            for handle in newItem.handles:
                handle['item'].pen.setWidth(self.DEFAULT_MARKER_SIZE)

            self.displayArea.addItem(newItem)
            self.displayArea.removeItem(roi1)
            self.displayArea.removeItem(roi2)
            if index1 > index2:
                self.displayData.remove(self.displayData[index1])
                self.displayData.remove(self.displayData[index2])
            else:
                self.displayData.remove(self.displayData[index2])
                self.displayData.remove(self.displayData[index1])

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
