"""USDJPY research-only invariant and no-lookahead smoke tests."""
import unittest
import numpy as np
import pandas as pd
from research_usdjpy.engine import config,signals,simulate,stats,TOTAL

class TestResearch(unittest.TestCase):
    def test_deterministic_bounded(self):
        self.assertEqual(config(0),config(0))
        self.assertRaises(ValueError,config,TOTAL)

    def frame(self):
        n=140
        x=np.repeat(150.0,n)
        t=pd.date_range("2025-01-06 07:00",periods=n,freq="5min",tz="UTC")
        d=pd.DataFrame({"timestamp_utc":t,"tick_count":[30]*n})
        for p,bias in (("bid",0),("ask",.012)):
            for field in ("open","close","high","low"):
                d[p+"_"+field]=x+bias
        return d

    def test_flat_is_no_trade(self):
        d=self.frame()
        for i in range(4):
            self.assertEqual(simulate(d,config(i)),[])

    def test_past_only_signal(self):
        d=self.frame()
        s1,_=signals(d,config(0))
        d.loc[len(d)-1,["bid_close","ask_close","bid_high","ask_high"]]+=1
        s2,_=signals(d,config(0))
        self.assertTrue(np.array_equal(s1[:-1],s2[:-1]))

    def test_statistics(self):
        trades=[{"exit_utc":"2025-01-02T08:00:00Z","pnl_usd":2.0},
                {"exit_utc":"2025-01-03T08:00:00Z","pnl_usd":-1.0}]
        m=stats(trades)
        self.assertEqual(m["net_usd"],1)
        self.assertEqual(m["profit_factor"],2)
        self.assertEqual(m["max_drawdown_usd"],1)

if __name__=="__main__":unittest.main()
