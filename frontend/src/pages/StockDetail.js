import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box, Card, CardContent, Grid, Typography, Paper, Button,
  TextField, CircularProgress, Tabs, Tab, Divider, Alert,
  Snackbar, InputAdornment
} from '@mui/material';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  TimeScale
} from 'chart.js';
import 'chartjs-adapter-date-fns';
import { ko } from 'date-fns/locale';

// 서비스 임포트
import { stockService } from '../services/stockService';
import { portfolioService } from '../services/portfolioService';

// 차트 컴포넌트 등록
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  TimeScale,
  Title,
  Tooltip,
  Legend
);

// 탭 패널 컴포넌트
function TabPanel(props) {
  const { children, value, index, ...other } = props;

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`stock-tabpanel-${index}`}
      aria-labelledby={`stock-tab-${index}`}
      {...other}
    >
      {value === index && (
        <Box sx={{ p: 2 }}>
          {children}
        </Box>
      )}
    </div>
  );
}

const StockDetail = () => {
  const { market, symbol } = useParams();
  const navigate = useNavigate();

  // 상태 변수
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [stockData, setStockData] = useState(null);
  const [stockAnalysis, setStockAnalysis] = useState(null);
  const [chartData, setChartData] = useState(null);
  const [selectedPeriod, setSelectedPeriod] = useState('1mo');
  const [tabValue, setTabValue] = useState(0);
  const [orderType, setOrderType] = useState('buy');
  const [quantity, setQuantity] = useState(1);
  const [price, setPrice] = useState('');
  const [marketOrder, setMarketOrder] = useState(true);
  const [orderStatus, setOrderStatus] = useState(null);
  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState('');
  const [snackbarSeverity, setSnackbarSeverity] = useState('info');

  // 데이터 로드 함수
  const loadStockData = async () => {
    setLoading(true);
    setError(null);

    try {
      // 주식 데이터 로드
      const data = await stockService.getStockData(symbol, market, selectedPeriod);
      setStockData(data);

      // 차트 데이터 준비
      prepareChartData(data.data);

      // 분석 데이터 로드
      const analysis = await stockService.analyzeStock(symbol, market, 'general');
      setStockAnalysis(analysis);

      // 초기 가격 설정
      if (data.latest_price) {
        setPrice(data.latest_price.toString());
      }
    } catch (err) {
      console.error('주식 데이터 로드 중 오류 발생:', err);
      setError('주식 데이터를 불러오는 중 문제가 발생했습니다.');
    } finally {
      setLoading(false);
    }
  };

  // 컴포넌트 마운트 시 데이터 로드
  useEffect(() => {
    loadStockData();
  }, [market, symbol, selectedPeriod]);

  // 차트 데이터 준비
  const prepareChartData = (data) => {
    if (!data || data.length === 0) return;

    const prices = data.map(item => ({
      x: new Date(item.Date),
      y: item.Close
    }));

    const dataset = {
      labels: data.map(item => item.Date),
      datasets: [
        {
          label: '종가',
          data: prices,
          borderColor: 'rgb(53, 162, 235)',
          backgroundColor: 'rgba(53, 162, 235, 0.5)',
          tension: 0.1
        }
      ]
    };

    setChartData(dataset);
  };

  // 탭 변경 핸들러
  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
  };

  // 주기 변경 핸들러
  const handlePeriodChange = (period) => {
    setSelectedPeriod(period);
  };

  // 주문 유형 변경 핸들러
  const handleOrderTypeChange = (type) => {
    setOrderType(type);
  };

  // 주문 실행 핸들러
  const handlePlaceOrder = async () => {
    try {
      // 유효성 검사
      if (!quantity || quantity <= 0) {
        showSnackbar('수량을 올바르게 입력해주세요.', 'error');
        return;
      }

      if (!marketOrder && (!price || parseFloat(price) <= 0)) {
        showSnackbar('가격을 올바르게 입력해주세요.', 'error');
        return;
      }

      // 주문 데이터 준비
      const orderData = {
        symbol,
        market,
        order_type: orderType,
        quantity: parseInt(quantity),
        price: marketOrder ? null : parseFloat(price),
        market_order: marketOrder
      };

      // 주문 실행
      setOrderStatus('pending');
      const result = await portfolioService.placeOrder(orderData);
      
      // 주문 결과 처리
      setOrderStatus('success');
      showSnackbar(`주문이 성공적으로 실행되었습니다. (${orderType === 'buy' ? '매수' : '매도'} ${quantity}주)`, 'success');
      
      // 주문 후 폼 초기화
      setQuantity(1);
      if (stockData?.latest_price) {
        setPrice(stockData.latest_price.toString());
      } else {
        setPrice('');
      }
    } catch (err) {
      console.error('주문 실행 중 오류 발생:', err);
      setOrderStatus('error');
      showSnackbar(`주문 실행 중 오류가 발생했습니다: ${err.response?.data?.detail || err.message}`, 'error');
    }
  };

  // 스낵바 표시 함수
  const showSnackbar = (message, severity) => {
    setSnackbarMessage(message);
    setSnackbarSeverity(severity);
    setSnackbarOpen(true);
  };

  // 스낵바 닫기 핸들러
  const handleSnackbarClose = () => {
    setSnackbarOpen(false);
  };

  // 로딩 중인 경우
  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '80vh' }}>
        <CircularProgress />
      </Box>
    );
  }

  // 오류가 발생한 경우
  if (error) {
    return (
      <Box sx={{ p: 3, textAlign: 'center' }}>
        <Typography variant="h6" color="error" gutterBottom>
          {error}
        </Typography>
        <Button variant="contained" onClick={loadStockData}>
          다시 시도
        </Button>
      </Box>
    );
  }

  return (
    <Box sx={{ flexGrow: 1, p: 1 }}>
      {/* 종목 헤더 정보 */}
      <Paper sx={{ p: 2, mb: 3 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
          <Box>
            <Typography variant="h4" gutterBottom>
              {stockData?.symbol} 
              {market === 'KR' ? ' - 한국 주식' : ' - 미국 주식'}
            </Typography>
            <Typography variant="body1" color="text.secondary">
              현재가: {market === 'KR' ? `${stockData?.latest_price?.toLocaleString()} 원` : `$${stockData?.latest_price?.toLocaleString()}`}
            </Typography>
          </Box>
          
          <Box>
            <Button variant="outlined" onClick={() => navigate(-1)}>
              뒤로 가기
            </Button>
          </Box>
        </Box>
      </Paper>

      {/* 주식 차트 및 분석 */}
      <Grid container spacing={3}>
        <Grid item xs={12} lg={8}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              가격 차트
            </Typography>
            
            <Box sx={{ mb: 2, display: 'flex', gap: 1 }}>
              <Button 
                size="small"
                variant={selectedPeriod === '1d' ? 'contained' : 'outlined'} 
                onClick={() => handlePeriodChange('1d')}
              >
                1일
              </Button>
              <Button 
                size="small"
                variant={selectedPeriod === '1w' ? 'contained' : 'outlined'} 
                onClick={() => handlePeriodChange('1w')}
              >
                1주
              </Button>
              <Button 
                size="small"
                variant={selectedPeriod === '1mo' ? 'contained' : 'outlined'} 
                onClick={() => handlePeriodChange('1mo')}
              >
                1개월
              </Button>
              <Button 
                size="small"
                variant={selectedPeriod === '3mo' ? 'contained' : 'outlined'} 
                onClick={() => handlePeriodChange('3mo')}
              >
                3개월
              </Button>
              <Button 
                size="small"
                variant={selectedPeriod === '6mo' ? 'contained' : 'outlined'} 
                onClick={() => handlePeriodChange('6mo')}
              >
                6개월
              </Button>
              <Button 
                size="small"
                variant={selectedPeriod === '1y' ? 'contained' : 'outlined'} 
                onClick={() => handlePeriodChange('1y')}
              >
                1년
              </Button>
              <Button 
                size="small"
                variant={selectedPeriod === '5y' ? 'contained' : 'outlined'} 
                onClick={() => handlePeriodChange('5y')}
              >
                5년
              </Button>
            </Box>
            
            {chartData ? (
              <Box sx={{ height: 400 }}>
                <Line
                  data={chartData}
                  options={{
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                      x: {
                        type: 'time',
                        time: {
                          unit: selectedPeriod === '1d' ? 'hour' : 
                                 selectedPeriod === '1w' ? 'day' : 
                                 selectedPeriod === '1mo' ? 'day' : 
                                 selectedPeriod === '3mo' ? 'week' : 'month',
                          displayFormats: {
                            hour: 'HH:mm',
                            day: 'MM-dd',
                            week: 'MM-dd',
                            month: 'yyyy-MM'
                          },
                          tooltipFormat: 'yyyy-MM-dd'
                        },
                        adapters: {
                          date: {
                            locale: ko
                          }
                        },
                        title: {
                          display: true,
                          text: '날짜'
                        }
                      },
                      y: {
                        title: {
                          display: true,
                          text: '가격'
                        }
                      }
                    },
                    plugins: {
                      tooltip: {
                        callbacks: {
                          label: function(context) {
                            let label = context.dataset.label || '';
                            if (label) {
                              label += ': ';
                            }
                            if (context.parsed.y !== null) {
                              label += market === 'KR' ? 
                                `${context.parsed.y.toLocaleString()} 원` : 
                                `$${context.parsed.y.toLocaleString()}`;
                            }
                            return label;
                          }
                        }
                      }
                    }
                  }}
                />
              </Box>
            ) : (
              <Typography variant="body1" color="text.secondary" align="center">
                차트 데이터가 없습니다.
              </Typography>
            )}
          </Paper>
        </Grid>
        
        <Grid item xs={12} lg={4}>
          <Paper sx={{ p: 2 }}>
            <Tabs value={tabValue} onChange={handleTabChange} centered>
              <Tab label="주문" />
              <Tab label="분석" />
            </Tabs>
            
            {/* 주문 탭 */}
            <TabPanel value={tabValue} index={0}>
              <Box sx={{ display: 'flex', mb: 2 }}>
                <Button 
                  fullWidth 
                  variant={orderType === 'buy' ? 'contained' : 'outlined'} 
                  color="primary"
                  onClick={() => handleOrderTypeChange('buy')}
                  sx={{ mr: 1 }}
                >
                  매수
                </Button>
                <Button 
                  fullWidth 
                  variant={orderType === 'sell' ? 'contained' : 'outlined'} 
                  color="error"
                  onClick={() => handleOrderTypeChange('sell')}
                >
                  매도
                </Button>
              </Box>
              
              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" gutterBottom>
                  수량
                </Typography>
                <TextField
                  fullWidth
                  type="number"
                  size="small"
                  value={quantity}
                  onChange={(e) => setQuantity(e.target.value)}
                  inputProps={{ min: 1 }}
                />
              </Box>
              
              <Box sx={{ mb: 3 }}>
                <Typography variant="body2" gutterBottom>
                  가격
                </Typography>
                <TextField
                  fullWidth
                  type="number"
                  size="small"
                  value={price}
                  onChange={(e) => setPrice(e.target.value)}
                  disabled={marketOrder}
                  InputProps={{
                    endAdornment: <InputAdornment position="end">{market === 'KR' ? '원' : 'USD'}</InputAdornment>,
                  }}
                />
                
                <Box sx={{ mt: 1 }}>
                  <Button 
                    size="small" 
                    variant={marketOrder ? 'contained' : 'outlined'} 
                    onClick={() => setMarketOrder(true)}
                    sx={{ mr: 1 }}
                  >
                    시장가
                  </Button>
                  <Button 
                    size="small" 
                    variant={!marketOrder ? 'contained' : 'outlined'} 
                    onClick={() => setMarketOrder(false)}
                  >
                    지정가
                  </Button>
                </Box>
              </Box>
              
              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" gutterBottom>
                  예상 금액
                </Typography>
                <Typography variant="h6">
                  {market === 'KR' ? 
                    `${(parseFloat(price || 0) * quantity).toLocaleString()} 원` : 
                    `$${(parseFloat(price || 0) * quantity).toLocaleString()}`}
                </Typography>
              </Box>
              
              <Button 
                fullWidth 
                variant="contained" 
                onClick={handlePlaceOrder}
                disabled={orderStatus === 'pending'}
                color={orderType === 'buy' ? 'primary' : 'error'}
              >
                {orderStatus === 'pending' ? '주문 처리 중...' : (orderType === 'buy' ? '매수' : '매도')}
              </Button>
              
              {orderStatus === 'error' && (
                <Alert severity="error" sx={{ mt: 2 }}>
                  주문 처리 중 오류가 발생했습니다.
                </Alert>
              )}
              
              {orderStatus === 'success' && (
                <Alert severity="success" sx={{ mt: 2 }}>
                  주문이 성공적으로 처리되었습니다.
                </Alert>
              )}
            </TabPanel>
            
            {/* 분석 탭 */}
            <TabPanel value={tabValue} index={1}>
              {stockAnalysis ? (
                <Box>
                  <Typography variant="subtitle1" gutterBottom>
                    AI 분석 결과
                  </Typography>
                  <Typography variant="body2" paragraph>
                    {stockAnalysis.analysis}
                  </Typography>
                  
                  {stockAnalysis.trading_signals && stockAnalysis.trading_signals.length > 0 && (
                    <>
                      <Divider sx={{ my: 2 }} />
                      <Typography variant="subtitle1" gutterBottom>
                        매매 신호
                      </Typography>
                      {stockAnalysis.trading_signals.map((signal, index) => (
                        <Card key={index} variant="outlined" sx={{ mb: 1 }}>
                          <CardContent sx={{ py: 1, '&:last-child': { pb: 1 } }}>
                            <Typography variant="body2" color={signal.type === 'BUY' ? 'success.main' : 'error.main'} gutterBottom>
                              {signal.type === 'BUY' ? '매수' : '매도'} 신호 (신뢰도: {(signal.confidence * 100).toFixed(1)}%)
                            </Typography>
                            <Typography variant="body2">
                              {signal.analysis}
                            </Typography>
                          </CardContent>
                        </Card>
                      ))}
                    </>
                  )}
                </Box>
              ) : (
                <Typography variant="body1" color="text.secondary" align="center">
                  분석 데이터를 불러오는 중...
                </Typography>
              )}
            </TabPanel>
          </Paper>
        </Grid>
      </Grid>
      
      {/* 스낵바 알림 */}
      <Snackbar
        open={snackbarOpen}
        autoHideDuration={6000}
        onClose={handleSnackbarClose}
      >
        <Alert onClose={handleSnackbarClose} severity={snackbarSeverity} sx={{ width: '100%' }}>
          {snackbarMessage}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default StockDetail;