import React, { useState, useEffect, useContext } from 'react';
import { Container, Typography, Grid, Paper, Box, Table, TableBody, TableCell, 
  TableContainer, TableHead, TableRow, CircularProgress, Divider, Chip } from '@mui/material';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import TrendingDownIcon from '@mui/icons-material/TrendingDown';
import AccountBalanceWalletIcon from '@mui/icons-material/AccountBalanceWallet';
import ShowChartIcon from '@mui/icons-material/ShowChart';
import { AuthContext } from '../context/AuthContext';
import { portfolioService } from '../services/portfolioService';

const Portfolio = () => {
  const { token } = useContext(AuthContext);
  const [portfolioData, setPortfolioData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchPortfolioData = async () => {
      if (!token) return;
      
      setLoading(true);
      try {
        const data = await portfolioService.getPortfolio(token);
        setPortfolioData(data);
        setError(null);
      } catch (err) {
        setError('포트폴리오 데이터를 불러오는 중 오류가 발생했습니다.');
        console.error('포트폴리오 데이터 조회 오류:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchPortfolioData();
  }, [token]);

  const formatCurrency = (value, market = 'KR') => {
    if (value === undefined || value === null) return '-';
    return new Intl.NumberFormat('ko-KR', {
      style: 'currency',
      currency: market === 'KR' ? 'KRW' : 'USD',
      maximumFractionDigits: market === 'KR' ? 0 : 2
    }).format(value);
  };

  const formatPercent = (value) => {
    if (value === undefined || value === null) return '-';
    return `${value > 0 ? '+' : ''}${value.toFixed(2)}%`;
  };

  const getChangeColor = (changePercent) => {
    if (!changePercent && changePercent !== 0) return 'text.primary';
    return changePercent > 0 ? 'error.main' : changePercent < 0 ? 'primary.main' : 'text.primary';
  };

  const getChangeIcon = (changePercent) => {
    if (!changePercent && changePercent !== 0) return null;
    if (changePercent > 0) return <TrendingUpIcon color="error" fontSize="small" />;
    if (changePercent < 0) return <TrendingDownIcon color="primary" fontSize="small" />;
    return null;
  };

  // 수익률 계산
  const calculateProfitLoss = (position) => {
    if (!position.현재가 || !position.평균단가 || position.평균단가 <= 0) return 0;
    return ((position.현재가 / position.평균단가) - 1) * 100;
  };

  // 평가금액 계산
  const calculateCurrentValue = (position) => {
    if (!position.현재가 || !position.보유수량) return 0;
    return position.현재가 * position.보유수량;
  };

  // 총 평가금액 계산
  const calculateTotalValue = (positions) => {
    if (!positions || positions.length === 0) return 0;
    return positions.reduce((sum, position) => sum + calculateCurrentValue(position), 0);
  };

  // 총 평가손익 계산
  const calculateTotalProfitLoss = (positions) => {
    if (!positions || positions.length === 0) return 0;
    const totalBuyValue = positions.reduce((sum, position) => 
      sum + (position.평균단가 * position.보유수량), 0);
    const totalCurrentValue = calculateTotalValue(positions);
    return ((totalCurrentValue / totalBuyValue) - 1) * 100;
  };

  if (loading) {
    return (
      <Container sx={{ py: 4, textAlign: 'center' }}>
        <CircularProgress />
        <Typography variant="body1" sx={{ mt: 2 }}>포트폴리오 데이터를 불러오는 중...</Typography>
      </Container>
    );
  }

  if (error) {
    return (
      <Container sx={{ py: 4, textAlign: 'center' }}>
        <Typography color="error">{error}</Typography>
      </Container>
    );
  }

  if (!portfolioData) {
    return (
      <Container sx={{ py: 4, textAlign: 'center' }}>
        <Typography>포트폴리오 데이터가 없습니다.</Typography>
      </Container>
    );
  }

  const { account_balance, positions, positions_count } = portfolioData;
  const totalValue = calculateTotalValue(positions);
  const totalProfitLoss = calculateTotalProfitLoss(positions);
  
  return (
    <Container sx={{ py: 4 }}>
      <Typography variant="h4" component="h1" gutterBottom>
        포트폴리오
      </Typography>
      
      <Grid container spacing={3} sx={{ mb: 4 }}>
        {/* 계좌 요약 정보 */}
        <Grid item xs={12} md={6}>
          <Paper elevation={2} sx={{ p: 3, height: '100%' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
              <AccountBalanceWalletIcon sx={{ mr: 1, color: 'primary.main' }} />
              <Typography variant="h6">계좌 요약</Typography>
            </Box>
            <Box sx={{ mb: 2 }}>
              <Typography variant="subtitle2" color="text.secondary">총 자산</Typography>
              <Typography variant="h5">{formatCurrency(account_balance?.총평가금액)}</Typography>
            </Box>
            <Box sx={{ mb: 2 }}>
              <Typography variant="subtitle2" color="text.secondary">예수금</Typography>
              <Typography variant="h6">{formatCurrency(account_balance?.예수금)}</Typography>
            </Box>
            <Box>
              <Typography variant="subtitle2" color="text.secondary">출금 가능금액</Typography>
              <Typography variant="h6">{formatCurrency(account_balance?.출금가능금액)}</Typography>
            </Box>
          </Paper>
        </Grid>
        
        {/* 포트폴리오 요약 */}
        <Grid item xs={12} md={6}>
          <Paper elevation={2} sx={{ p: 3, height: '100%' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
              <ShowChartIcon sx={{ mr: 1, color: 'secondary.main' }} />
              <Typography variant="h6">투자 현황</Typography>
            </Box>
            <Box sx={{ mb: 2 }}>
              <Typography variant="subtitle2" color="text.secondary">총 평가금액</Typography>
              <Typography variant="h5">{formatCurrency(totalValue)}</Typography>
            </Box>
            <Box sx={{ mb: 2 }}>
              <Typography variant="subtitle2" color="text.secondary">총 수익률</Typography>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                {getChangeIcon(totalProfitLoss)}
                <Typography 
                  variant="h6" 
                  color={getChangeColor(totalProfitLoss)}
                >
                  {formatPercent(totalProfitLoss)}
                </Typography>
              </Box>
            </Box>
            <Box>
              <Typography variant="subtitle2" color="text.secondary">보유 종목 수</Typography>
              <Typography variant="h6">{positions_count || 0}개</Typography>
            </Box>
          </Paper>
        </Grid>
      </Grid>
      
      {/* 보유 종목 목록 */}
      <Paper elevation={2} sx={{ p: 3, mb: 4 }}>
        <Typography variant="h6" sx={{ mb: 2 }}>보유 종목</Typography>
        
        {positions && positions.length > 0 ? (
          <TableContainer>
            <Table sx={{ minWidth: 650 }} aria-label="보유 종목 목록">
              <TableHead>
                <TableRow>
                  <TableCell>종목코드</TableCell>
                  <TableCell>종목명</TableCell>
                  <TableCell align="right">현재가</TableCell>
                  <TableCell align="right">평균단가</TableCell>
                  <TableCell align="right">수량</TableCell>
                  <TableCell align="right">평가금액</TableCell>
                  <TableCell align="right">수익률</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {positions.map((position) => {
                  const profitLoss = calculateProfitLoss(position);
                  const currentValue = calculateCurrentValue(position);
                  return (
                    <TableRow key={position.종목코드}>
                      <TableCell component="th" scope="row">
                        {position.종목코드}
                      </TableCell>
                      <TableCell>{position.종목명}</TableCell>
                      <TableCell align="right">{formatCurrency(position.현재가)}</TableCell>
                      <TableCell align="right">{formatCurrency(position.평균단가)}</TableCell>
                      <TableCell align="right">{position.보유수량?.toLocaleString() || '-'}</TableCell>
                      <TableCell align="right">{formatCurrency(currentValue)}</TableCell>
                      <TableCell 
                        align="right"
                        sx={{ color: getChangeColor(profitLoss) }}
                      >
                        {getChangeIcon(profitLoss)}
                        {formatPercent(profitLoss)}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>
        ) : (
          <Typography variant="body1" sx={{ textAlign: 'center', py: 4 }}>
            보유 종목이 없습니다.
          </Typography>
        )}
      </Paper>
    </Container>
  );
};

export default Portfolio;