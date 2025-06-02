import React, { useState, useEffect, useContext } from 'react';
import { Link } from 'react-router-dom';
import { Container, Typography, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper, 
  TextField, InputAdornment, Box, FormControl, InputLabel, Select, MenuItem, CircularProgress, Chip } from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import TrendingDownIcon from '@mui/icons-material/TrendingDown';
import { AuthContext } from '../context/AuthContext';
import { stockService } from '../services/stockService';

const StockList = () => {
  const { token } = useContext(AuthContext);
  const [stocks, setStocks] = useState([]);
  const [filteredStocks, setFilteredStocks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [marketFilter, setMarketFilter] = useState('KR');

  useEffect(() => {
    const fetchStocks = async () => {
      if (!token) return;
      
      setLoading(true);
      try {
        const response = await stockService.getStockList(marketFilter, token);
        setStocks(response.stocks || []);
        setFilteredStocks(response.stocks || []);
        setError(null);
      } catch (err) {
        setError('주식 목록을 불러오는 중 오류가 발생했습니다.');
        console.error('주식 목록 조회 오류:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchStocks();
  }, [token, marketFilter]);

  useEffect(() => {
    // 검색어에 따라 주식 목록 필터링
    if (searchTerm.trim() === '') {
      setFilteredStocks(stocks);
    } else {
      const filtered = stocks.filter(stock => 
        stock.code?.toLowerCase().includes(searchTerm.toLowerCase()) || 
        stock.name?.toLowerCase().includes(searchTerm.toLowerCase())
      );
      setFilteredStocks(filtered);
    }
  }, [searchTerm, stocks]);

  const getChangeColor = (changePercent) => {
    if (!changePercent) return 'text.primary';
    return changePercent > 0 ? 'error.main' : changePercent < 0 ? 'primary.main' : 'text.primary';
  };

  const getChangeIcon = (changePercent) => {
    if (!changePercent) return null;
    if (changePercent > 0) return <TrendingUpIcon color="error" fontSize="small" />;
    if (changePercent < 0) return <TrendingDownIcon color="primary" fontSize="small" />;
    return null;
  };

  const formatCurrency = (value, market) => {
    if (!value) return '-';
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

  const getRsiColor = (rsi) => {
    if (rsi === undefined || rsi === null) return 'text.primary';
    if (rsi >= 70) return 'error.main';
    if (rsi <= 30) return 'success.main';
    return 'text.primary';
  };

  const getRsiChip = (rsi) => {
    if (rsi === undefined || rsi === null) return null;

    let color = 'default';
    let label = 'RSI: ' + rsi.toFixed(1);

    if (rsi >= 70) {
      color = 'error';
      label = '과매수: ' + rsi.toFixed(1);
    } else if (rsi <= 30) {
      color = 'success';
      label = '과매도: ' + rsi.toFixed(1);
    }

    return <Chip label={label} color={color} size="small" />;
  };

  if (loading && stocks.length === 0) {
    return (
      <Container sx={{ py: 4, textAlign: 'center' }}>
        <CircularProgress />
        <Typography variant="body1" sx={{ mt: 2 }}>주식 데이터를 불러오는 중...</Typography>
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

  return (
    <Container sx={{ py: 4 }}>
      <Typography variant="h4" component="h1" gutterBottom>
        주식 목록
      </Typography>
      
      <Box sx={{ mb: 3, display: 'flex', flexDirection: { xs: 'column', sm: 'row' }, gap: 2 }}>
        <FormControl variant="outlined" size="small" sx={{ minWidth: 120 }}>
          <InputLabel id="market-filter-label">시장</InputLabel>
          <Select
            labelId="market-filter-label"
            id="market-filter"
            value={marketFilter}
            onChange={(e) => setMarketFilter(e.target.value)}
            label="시장"
          >
            <MenuItem value="KR">한국주식</MenuItem>
            <MenuItem value="US">미국주식</MenuItem>
          </Select>
        </FormControl>
        
        <TextField
          placeholder="종목 검색..."
          variant="outlined"
          fullWidth
          size="small"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon />
              </InputAdornment>
            ),
          }}
        />
      </Box>
      
      {filteredStocks.length === 0 ? (
        <Typography variant="body1" sx={{ textAlign: 'center', py: 4 }}>
          {searchTerm ? '검색 결과가 없습니다.' : '주식 목록이 없습니다.'}
        </Typography>
      ) : (
        <TableContainer component={Paper}>
          <Table sx={{ minWidth: 650 }} aria-label="주식 목록">
            <TableHead>
              <TableRow sx={{ backgroundColor: 'background.paper' }}>
                <TableCell>종목코드</TableCell>
                <TableCell>종목명</TableCell>
                <TableCell align="right">현재가</TableCell>
                <TableCell align="right">변동률</TableCell>
                <TableCell align="right">기술지표</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {filteredStocks.map((stock) => (
                <TableRow 
                  key={stock.code}
                  hover
                  sx={{ 
                    textDecoration: 'none',
                    '&:hover': { backgroundColor: 'action.hover' },
                    cursor: 'pointer'
                  }}
                  onClick={() => window.location.href = `/stocks/${marketFilter}/${stock.code}`}
                >
                  <TableCell component="th" scope="row">
                    {stock.code}
                  </TableCell>
                  <TableCell>{stock.name || stock.code}</TableCell>
                  <TableCell align="right">
                    {formatCurrency(stock.current_price, marketFilter)}
                  </TableCell>
                  <TableCell 
                    align="right"
                    sx={{ color: getChangeColor(stock.change_percent) }}
                  >
                    {getChangeIcon(stock.change_percent)}
                    {formatPercent(stock.change_percent)}
                  </TableCell>
                  <TableCell align="right" sx={{ color: getRsiColor(stock.rsi) }}>
                    {stock.rsi ? getRsiChip(stock.rsi) : '-'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Container>
  );
};

export default StockList;