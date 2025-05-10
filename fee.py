from datetime import date


class schedule:
    def __init__(self, startPeriod, limit, useESS):
        self.startPeriod = startPeriod
        self.limit = limit
        self.useESS = useESS


class profile:
    _id = "..."
    reservationId = "..."  # 예약 이후 변경되는 값
    chargingProfileKind = "ABSOLUTE"
    startSchedule = "2000-01-01T00:00:00Z"

    def setSchedule(self, startTime):
        if startTime < 10:
            self.startSchedule = str(date.today()) + "T0" + str(startTime) + ":00:00Z"
        else:
            self.startSchedule = str(date.today()) + "T" + str(startTime) + ":00:00Z"

    def clearSchedule(self):
        self.chargingSchedules = []

    def addSchedule(self, newSchedule):
        self.chargingSchedules.append(newSchedule)

    def testprint(self):  ## 테스트용 함수. 삭제 필요
        for i in self.chargingSchedules:
            print(str(i.startPeriod) + "초간 " + str(i.limit))


notReserved = []
notReserved.append(profile())
notReserved.append(profile())


def ESS_fee(StationNo):
    # SQL
    # return fee
    return 50  # test용; SQL문 추가 후 지울 것


def ESS_Power(StationNo):
    # SQL
    # return power
    return 10000  # test용; SQL문 추가 후 지울 것


def ToU_fee(Time):
    if Time < 8 or Time > 22:
        return 99
    elif Time < 14 or Time > 17:
        return 143
    else:
        return 166


def calcFee(startTime, chargeTime, chargePower, StationNo):
    # 고속충전: 50kWh / 완속충전: 30kWh
    # startTime 충전 시작 시각[단위: h]
    # chargeTime 충전 전체 시간[단위: s]
    # QuickTime 고속 충전 시간[단위: h]
    ESSfee = ESS_fee(StationNo)
    ESSPOW = ESS_Power(StationNo)

    QuickTime = int((chargePower - int(chargeTime / 3600) * 30000 + 19999) / 20000)
    print(QuickTime)  ## 테스트용
    feeSum = 0
    notReserved[StationNo - 1].setSchedule(startTime)
    notReserved[StationNo - 1].clearSchedule()
    if QuickTime < 0:
        QuickTime = int((chargePower + 29999) / 30000)
        print(QuickTime)  ## 테스트용
        minSum = 166 * QuickTime
        minSumTime = -1
        for i in range(0, QuickTime):
            feeSum = 0
            for j in range(startTime + i, startTime + QuickTime + i):
                feeSum += ToU_fee(j % 24)
            if feeSum < minSum:
                minSum = feeSum
                minSumTime = startTime + i

        if minSumTime > startTime:
            noCharging = schedule(minSumTime * 3600, 0, False)
            notReserved[StationNo - 1].addSchedule(noCharging)

        lowLevelCharging = schedule(int((chargePower * 3 + 24) / 25), 30000, False)
        notReserved[StationNo - 1].addSchedule(lowLevelCharging)

        return minSum
    else:
        for i in range(startTime, startTime + int((chargeTime + 3599) / 3600)):
            feeSum += ToU_fee(i)
            print(i, feeSum)  ## 테스트용
        feeSum += QuickTime * ESSfee

        if QuickTime > 0:
            highLevelCharging = schedule(QuickTime * 3600, 50000, True)
            notReserved[StationNo - 1].addSchedule(highLevelCharging)

        if chargeTime - QuickTime * 3600 > 0:
            lowLevelCharging = schedule(chargeTime - QuickTime * 3600, 30000, False)
            notReserved[StationNo - 1].addSchedule(lowLevelCharging)

        return feeSum


## 이하 테스트 코드
calcFee(10, 18000, 150000, 1)
calcFee(12, 7200, 80000, 2)
for i in notReserved:
    print("***")
    i.testprint()
print("***")
calcFee(15, 18000, 250000, 1)
calcFee(23, 10800, 130000, 2)
for i in notReserved:
    print("***")
    i.testprint()
print("***")
calcFee(12, 18000, 60000, 1)
calcFee(17, 18000, 60000, 2)
for i in notReserved:
    print("***")
    i.testprint()
print("***")
calcFee(7, 18000, 50000, 1)
calcFee(20, 18000, 40000, 2)
for i in notReserved:
    print("***")
    i.testprint()
print("***")
