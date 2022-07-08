from PyQt5 import QtCore, QtWidgets
from PyQt5.uic import loadUi
import pyqtgraph as pg

from collections import namedtuple
import numpy as np
import logging


UI_WIDGET_FILE = 'graphWidgetForm.ui'


class PolyWidget(QtWidgets.QWidget):

    DEFAULT_LINE_COLOR = (255, 0, 0, 255)
    DEFAULT_LINE_WIDTH = 3
    DEFAULT_LINE_STYLE = 'Solid'
    DEFAULT_MARKER_COLOR = (0, 0, 255, 255)
    DEFAULT_MARKER_SIZE = 10
    DEFAULT_MARKER_STYLE = 'o'
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

        # Инициализируем хранилище отображаемых полигонов
        self._init_displayData()

    @staticmethod
    def connectLogging(status):
        if status:
            logging.basicConfig(format="%(asctime)s :    %(levelname)s :    %(message)s", level=logging.INFO)

    def connectSignals(self):
        self.addPolyPushButton.clicked.connect(self.polyAddition)
        self.deletePolyPushButton.clicked.connect(self.polyDeletion)    # Только если кнопка удаления активирована
        self.polyListWidget.itemChanged.connect(self.polyItemChangedEvent)
        self.polyListWidget.itemClicked.connect(self.polyItemSelectedEvent)

        # Панель кастомизации полигонов (изначально деактивирована)
        self.lineColorButtonWidget.sigColorChanged.connect(self.lineColorChanged)
        self.markerColorButtonWidget.sigColorChanged.connect(self.markerColorChanged)
        self.polyFillColorButtonWidget.sigColorChanged.connect(self.fillColorChanged)
        self.lineStyleComboBox.activated.connect(self.lineStyleChanged)
        self.markerStyleComboBox.activated.connect(self.markerStyleChanged)
        self.lineWidthSpinBox.valueChanged.connect(self.lineWidthChanged)
        self.markerSizeSpinBox.valueChanged.connect(self.markerSizeChanged)

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
             "fillcolor"]
        )

    # ~~~ Методы, работающие с элементами в polyListWidget ~~~ #

    def polyAddition(self):
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

        # Создаем новый полигон как объект структуры customPolygonStructure
        newPolygon = self.customPolygonStructure(
            newPolygonAsItem.data(1),
            newPolygonAsItem.text(),
            [],
            [],
            self.DEFAULT_LINE_COLOR,
            self.DEFAULT_LINE_WIDTH,
            self.DEFAULT_LINE_STYLE,
            self.DEFAULT_MARKER_COLOR,
            self.DEFAULT_MARKER_SIZE,
            self.DEFAULT_MARKER_STYLE,
            self.DEFAULT_FILL_COLOR
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

    def polyDeletion(self):
        """
        Данный метод реализует удаление выбранного Item'а из QListWidget'а и из displayArea
        """

        self.selectedFlag = True

        # Определяем, какой сейчас Item selected и удаляем его из QListWidget'а
        selectedItem = self.polyListWidget.currentItem()
        self.polyListWidget.takeItem(self.polyListWidget.row(selectedItem))

        # Удаляем его также из displayArea
        for i in range(len(self.displayData)):
            if self.displayData[i].key_id == selectedItem.data(1):
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
        # Добавим возможность Select и Deselect Item
        if self._isItemSelected(item):
            item.setSelected(True)
            # Активируем все функции кастомизации области
            self.setItemCustomizationButtonsActive(True)
            self.fillItemCustomizationButtons(item)
            return
        self.setItemCustomizationButtonsActive(False)

    # ~~~ Методы, обрабатывающие сигналы от панели кастомизации полигонов ~~~ #

    def lineColorChanged(self):
        """
        Метод, меняющий цвет линий выбранного полигона
        """

        index = self.findItemIndexInData(self.polyListWidget.currentItem())
        self.displayData[index] = \
            self.displayData[index]._replace(linecolor=self.lineColorButtonWidget.color(mode='byte'))

        # Информация
        logging.info(f"Ключ {self.displayData[index].key_id}. Цвет линий элемента {self.displayData[index].name} "
                     f"изменен на {self.displayData[index].linecolor}")

    def markerColorChanged(self):
        """
        Метод, меняющий цвет точек(узлов) выбранного полигона
        """

        index = self.findItemIndexInData(self.polyListWidget.currentItem())
        self.displayData[index] = \
            self.displayData[index]._replace(markercolor=self.markerColorButtonWidget.color(mode='byte'))

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

        index = self.findItemIndexInData(self.polyListWidget.currentItem())
        self.displayData[index] = \
            self.displayData[index]._replace(linestyle=self.lineStyleComboBox.currentText())

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

        index = self.findItemIndexInData(self.polyListWidget.currentItem())
        self.displayData[index] = \
            self.displayData[index]._replace(linewidth=self.lineWidthSpinBox.value())

        # Информация
        logging.info(f"Ключ {self.displayData[index].key_id}. Толщина линий элемента {self.displayData[index].name} "
                     f"изменена на {self.displayData[index].linewidth}")

    def markerSizeChanged(self):
        """
        Метод, изменяющий размер точек (узлов) в зависимости от числа в markerSizeSpinBox
        """

        index = self.findItemIndexInData(self.polyListWidget.currentItem())
        self.displayData[index] = \
            self.displayData[index]._replace(markersize=self.markerSizeSpinBox.value())

        # Информация
        logging.info(f"Ключ {self.displayData[index].key_id}. Толщина линий элемента {self.displayData[index].name} "
                     f"изменена на {self.displayData[index].markersize}")

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
        self.polyFillColorButtonWidget.setEnabled(status)
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
            self.polyFillColorButtonWidget.setColor(selectedItemFromData.fillcolor)

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

    #...





