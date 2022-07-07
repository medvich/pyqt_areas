from PyQt5 import QtCore, QtWidgets
from PyQt5.uic import loadUi
import pyqtgraph as pg

from collections import namedtuple
import numpy as np
import logging


UI_WIDGET_FILE = 'graphWidgetForm.ui'


class PolyWidget(QtWidgets.QWidget):

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        loadUi(UI_WIDGET_FILE, self)

        # Подключим вывод в консоль о произведенных действиях (при необходимости)
        self.connectLogging(True)

        # Подключим сигналы от кнопок
        self.connectSignals()

        # Инициализируем хранилище отображаемых полигонов
        self._init_displayData()

    @staticmethod
    def connectLogging(log):
        if log:
            logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.INFO)

    def connectSignals(self):
        self.addPolyPushButton.clicked.connect(self.polyAddition)
        self.deletePolyPushButton.clicked.connect(self.polyDeletion)    # Только если кнопка удаления активирована
        self.polyListWidget.itemChanged.connect(self.polyItemChangedEvent)
        self.polyListWidget.itemClicked.connect(self.polyItemSelectedEvent)

    def _init_displayData(self):
        self.key_id = 0
        self.displayData = []
        self.customPolygonStructure = namedtuple("customPolygonStructure", ["key_id", "name", "exterior", "interiors"])

    #######

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
        newPolygon = self.customPolygonStructure(newPolygonAsItem.data(1), newPolygonAsItem.text(), [], [])
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

        # ОпределяемЮ какой сейчас Item selected и удаляем его из QListWidget'а
        selectedItem = self.polyListWidget.currentItem()
        self.polyListWidget.takeItem(self.polyListWidget.row(selectedItem))

        # Удаляем его также из displayArea
        for i in range(len(self.displayData)):
            if self.displayData[i].key_id == selectedItem.data(1):
                self.displayData.remove(self.displayData[i])

                # Информация
                logging.info(f"Ключ {selectedItem.data(1)}. Элемент {selectedItem.text()} удален")

                # Disabl'им кнопку удаления если ни один элемент не selected во избежания лишних тыканий и
                # выползания ошибок
                if self.polyListWidget.currentItem() is None:
                    self.deletePolyPushButton.setEnabled(False)
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
        # Активируем кнопку удаления полигона
        self.deletePolyPushButton.setEnabled(True)

        # Активируем меню редактирования и информационное окно
        self.treeWidget.setEnabled(True)
        self.addExBoundPushButton.setEnabled(True)
        self.lineColorButtonWidget.setEnabled(True)
        self.markerColorButtonWidget.setEnabled(True)
        self.polyFillColorButtonWidget.setEnabled(True)
        self.lineStyleComboBox.setEnabled(True)
        self.markerStyleComboBox.setEnabled(True)
        self.lineWidthSpinBox.setEnabled(True)
        self.markerWidthSpinBox.setEnabled(True)

    #######

    def displayDataNames(self):
        """
        Возвращает имена полигонов из displayData
        """

        res = []
        for poly in self.displayData:
            res.append(poly.name)
        return res

    #...





