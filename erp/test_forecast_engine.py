from datetime import date
from decimal import Decimal
from django.test import SimpleTestCase

from erp.services.forecast_engine import forecast_months, month_after, project_supply


class ForecastEngineTests(SimpleTestCase):
    def test_no_data_short_history_and_zero_history_are_distinguished(self):
        empty=forecast_months([],12)
        self.assertEqual(empty['history_months'],0)
        self.assertEqual(empty['confidence'],'LOW')
        self.assertEqual(set(empty['forecast']),{'0.000000'})
        short=forecast_months([10,20],12)
        self.assertEqual(short['confidence'],'LOW')
        self.assertEqual(short['forecast'][0],'15.000000')
        self.assertFalse(short['confidence_is_probability'])
        self.assertEqual(short['backtest_mae'],{})
        self.assertEqual(forecast_months([0]*24,12)['confidence'],'MEDIUM')

    def test_trend_up_down_seasonality_and_rolling_validation(self):
        rising=forecast_months(list(range(10,34)),12)
        self.assertEqual(rising['method'],'TREND_12')
        self.assertEqual(rising['forecast'][0],'34.000000')
        self.assertEqual(rising['backtest_mae']['TREND_12'],'0.000000')
        falling=forecast_months(list(range(34,10,-1)),12)
        self.assertEqual(falling['method'],'TREND_12')
        self.assertTrue(all(Decimal(value)>=0 for value in falling['forecast']))
        pattern=[10,10,20,30,100,150,70,60,5,5,8,20]
        seasonal=forecast_months(pattern*3,12)
        self.assertEqual(seasonal['method'],'SEASONAL_NAIVE')
        self.assertEqual([Decimal(value) for value in seasonal['forecast']],list(map(Decimal,pattern)))
        self.assertNotIn('SEASONAL_NAIVE',forecast_months(pattern,12)['backtest_mae'])
        self.assertEqual(forecast_months([10]*36,12)['method'],'MEAN_12')

    def test_invalid_history_and_horizon_are_rejected(self):
        for value in ('NaN','Infinity',-1,True,'bad'):
            with self.subTest(value=value),self.assertRaises(ValueError):
                forecast_months([value],1)
        for horizon in (0,37,True):
            with self.assertRaises(ValueError):
                forecast_months([10],horizon)
        with self.assertRaises(ValueError):
            forecast_months([1]*121,12)
        self.assertEqual(month_after(date(2026,12,5)),date(2027,1,1))

    def project(self,**kwargs):
        values={'as_of':date(2027,1,1),'starts_on':date(2027,1,1),'ends_on':date(2027,1,31),
            'monthly_forecast':{'2027-01':31},'stock':[]}
        values.update(kwargs)
        return project_supply(**values)

    def test_exact_full_month_split_does_not_overorder_due_to_decimal_noise(self):
        result=self.project(monthly_forecast={'2027-01':100},purchase_factor=10)
        self.assertEqual(result['net_requirement'],'100.000000')
        self.assertEqual(result['purchase_quantity'],'10.000000')
        self.assertEqual(result['monthly']['2027-01']['demand'],'100.000000')

    def test_usable_stock_and_timely_incoming_reduce_the_need(self):
        result=self.project(stock=[{'id':'A','quantity':10}],incoming=[{'id':'B','quantity':10,'available_on':date(2027,1,11)}],safety_stock=5)
        self.assertEqual(result['covered_by_stock'],'10.000000')
        self.assertEqual(result['covered_by_orders'],'10.000000')
        self.assertEqual(result['net_requirement'],'16.000000')
        self.assertEqual(result['first_shortage'],'2027-01-21')

    def test_late_deliveries_do_not_cancel_earlier_shortages(self):
        result=self.project(incoming=[{'id':'A','quantity':31,'available_on':date(2027,1,21)}])
        self.assertEqual(result['shortage_in_horizon'],'20.000000')
        self.assertEqual(result['projected_end_balance'],'20.000000')
        self.assertEqual(result['first_shortage'],'2027-01-01')
        self.assertEqual(result['purchase_quantity'],'20.000000')

    def test_expiry_and_fefo_are_applied_by_day(self):
        result=self.project(stock=[{'id':'A','quantity':50,'expires_on':date(2027,1,10)}, {'id':'B','quantity':5}])
        self.assertEqual(result['covered_by_stock'],'15.000000')
        self.assertEqual(result['expired_unconsumed'],'40.000000')
        self.assertEqual(result['shortage_in_horizon'],'16.000000')
        self.assertEqual(result['first_shortage'],'2027-01-16')

    def test_regular_runs_are_not_added_twice_and_incremental_runs_are_added(self):
        result=self.project(commitments=[{'on':date(2027,1,20),'quantity':10,'incremental':False},
            {'on':date(2027,1,25),'quantity':5,'incremental':True}])
        self.assertEqual(result['monthly']['2027-01']['demand'],'36.000000')
        high=self.project(commitments=[{'on':date(2027,1,20),'quantity':50,'incremental':False}])
        self.assertEqual(high['monthly']['2027-01']['demand'],'50.000000')

    def test_shortage_before_annual_horizon_is_reported_separately(self):
        result=self.project(as_of=date(2026,12,1),monthly_forecast={'2026-12':31,'2027-01':31},
            stock=[{'id':'A','quantity':10}])
        self.assertEqual(result['shortage_before_horizon'],'21.000000')
        self.assertEqual(result['shortage_in_horizon'],'31.000000')
        self.assertEqual(result['purchase_quantity'],'31.000000')

    def test_package_multiple_minimum_order_and_surplus(self):
        result=self.project(purchase_factor=10,order_multiple=3,minimum_order=5)
        self.assertEqual(result['purchase_quantity'],'6.000000')
        self.assertEqual(result['base_quantity'],'60.000000')
        surplus=self.project(stock=[{'id':'A','quantity':100}],safety_stock=10,minimum_order=50)
        self.assertEqual(surplus['purchase_quantity'],'0.000000')
        self.assertEqual(surplus['projected_end_balance'],'69.000000')


    def test_projection_rejects_invalid_dates_units_sizes_and_missing_forecasts(self):
        invalid=[{'starts_on':date(2026,12,31)}, {'ends_on':date(2031,1,1)},
            {'purchase_factor':0}, {'order_multiple':0}, {'monthly_forecast':{}},
            {'incoming':[{'id':'X','quantity':1,'available_on':date(2026,12,31)}]},
            {'stock':[{'id':'X','quantity':1}]*10001},
            {'commitments':[{'on':date(2027,1,1),'quantity':1,'incremental':True}]*10001},
            {'purchase_factor':Decimal('.000001'),'monthly_forecast':{'2027-01':Decimal('999999999999')}}]
        for change in invalid:
            with self.subTest(change=str(change)[:90]),self.assertRaises(ValueError):
                self.project(**change)
        with self.assertRaises(ValueError):
            forecast_months([Decimal('20000000000')*i for i in range(1,37)],36)

    def test_expired_incoming_and_outside_horizon_commitments_are_not_available(self):
        result=self.project(incoming=[{'id':'X','quantity':100,'available_on':date(2027,1,2),'expires_on':date(2027,1,1)}],
            commitments=[{'on':date(2028,1,1),'quantity':100,'incremental':True}])
        self.assertEqual(result['purchase_quantity'],'31.000000')
        self.assertEqual(result['covered_by_orders'],'0.000000')
        with self.assertRaises(ValueError):
            self.project(stock=[{'id':'X','quantity':-1}])
        plateau=forecast_months([Decimal('900000000000')-Decimal('100000000000')*(8-i) for i in range(9)]+[Decimal('990000000000')]*9,36)
        self.assertEqual(plateau['method'],'RECENT_6')
        self.assertTrue(all(Decimal(value)==Decimal('990000000000') for value in plateau['forecast']))
