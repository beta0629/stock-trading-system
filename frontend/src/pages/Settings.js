import React, { useState, useEffect, useContext } from 'react';
import { Container, Typography, Paper, Box, Switch, FormControlLabel, 
  Divider, Button, Alert, Grid, Slider, CircularProgress,
  FormGroup, Snackbar, FormControl, Select, MenuItem, InputLabel } from '@mui/material';
import SettingsIcon from '@mui/icons-material/Settings';
import SaveIcon from '@mui/icons-material/Save';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import { AuthContext } from '../context/AuthContext';
import { systemService } from '../services/systemService';

const Settings = () => {
  const { token } = useContext(AuthContext);
  const [settings, setSettings] = useState({
    auto_trading_enabled: false,
    gpt_auto_trading_enabled: false,
    day_trading_mode: false,
    swing_trading_mode: false,
    telegram_enabled: false,
    kakao_enabled: false,
    max_position_per_stock: 10,
    max_amount_per_trade: 1000000,
    trading_strategy: 'balanced'
  });
  
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [notification, setNotification] = useState({
    open: false,
    message: '',
    severity: 'info'
  });

  useEffect(() => {
    const fetchSettings = async () => {
      if (!token) return;
      
      setLoading(true);
      try {
        const autoSettings = await systemService.getAutomationStatus(token);
        setSettings({
          auto_trading_enabled: autoSettings.auto_trading_enabled || false,
          gpt_auto_trading_enabled: autoSettings.gpt_auto_trading_enabled || false,
          day_trading_mode: autoSettings.day_trading_mode || false,
          swing_trading_mode: autoSettings.swing_trading_mode || false,
          telegram_enabled: autoSettings.telegram_enabled || false,
          kakao_enabled: autoSettings.kakao_enabled || false,
          max_position_per_stock: autoSettings.position_holding_config?.max_positions || 10,
          max_amount_per_trade: autoSettings.position_holding_config?.max_amount_per_stock || 1000000,
          trading_strategy: autoSettings.trading_strategy || 'balanced'
        });
        setError(null);
      } catch (err) {
        setError('설정을 불러오는 중 오류가 발생했습니다.');
        console.error('설정 조회 오류:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchSettings();
  }, [token]);

  const handleSwitchChange = (event) => {
    setSettings({
      ...settings,
      [event.target.name]: event.target.checked
    });
  };

  const handleSliderChange = (name) => (event, newValue) => {
    setSettings({
      ...settings,
      [name]: newValue
    });
  };

  const handleStrategyChange = (event) => {
    setSettings({
      ...settings,
      trading_strategy: event.target.value
    });
  };

  const saveSettings = async () => {
    if (!token) return;
    
    setSaving(true);
    try {
      await systemService.toggleAutomation(token, {
        auto_trading_enabled: settings.auto_trading_enabled,
        gpt_auto_trading_enabled: settings.gpt_auto_trading_enabled,
        day_trading_mode: settings.day_trading_mode,
        swing_trading_mode: settings.swing_trading_mode,
        telegram_enabled: settings.telegram_enabled,
        kakao_enabled: settings.kakao_enabled,
        max_position_per_stock: settings.max_position_per_stock,
        max_amount_per_trade: settings.max_amount_per_trade
      });
      
      setNotification({
        open: true,
        message: '설정이 성공적으로 저장되었습니다.',
        severity: 'success'
      });
    } catch (err) {
      setNotification({
        open: true,
        message: '설정 저장 중 오류가 발생했습니다: ' + (err.message || '알 수 없는 오류'),
        severity: 'error'
      });
      console.error('설정 저장 오류:', err);
    } finally {
      setSaving(false);
    }
  };

  const runTradingCycle = async () => {
    if (!token) return;
    
    setSaving(true);
    try {
      await systemService.runTradingCycle(token);
      
      setNotification({
        open: true,
        message: '트레이딩 사이클이 시작되었습니다.',
        severity: 'info'
      });
    } catch (err) {
      setNotification({
        open: true,
        message: '트레이딩 사이클 시작 중 오류가 발생했습니다: ' + (err.message || '알 수 없는 오류'),
        severity: 'error'
      });
      console.error('트레이딩 사이클 시작 오류:', err);
    } finally {
      setSaving(false);
    }
  };

  const closeNotification = () => {
    setNotification({ ...notification, open: false });
  };

  if (loading) {
    return (
      <Container sx={{ py: 4, textAlign: 'center' }}>
        <CircularProgress />
        <Typography variant="body1" sx={{ mt: 2 }}>설정을 불러오는 중...</Typography>
      </Container>
    );
  }

  return (
    <Container sx={{ py: 4 }}>
      <Typography variant="h4" component="h1" sx={{ mb: 4, display: 'flex', alignItems: 'center' }}>
        <SettingsIcon sx={{ mr: 1 }} />
        시스템 설정
      </Typography>
      
      {error && (
        <Alert severity="error" sx={{ mb: 4 }}>{error}</Alert>
      )}
      
      <Paper elevation={2} sx={{ p: 3, mb: 4 }}>
        <Typography variant="h6" gutterBottom>자동 매매 설정</Typography>
        <Divider sx={{ mb: 3 }} />
        
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <FormGroup>
              <FormControlLabel 
                control={
                  <Switch
                    checked={settings.auto_trading_enabled}
                    onChange={handleSwitchChange}
                    name="auto_trading_enabled"
                    color="primary"
                  />
                } 
                label="자동 매매 활성화"
              />
              <FormControlLabel 
                control={
                  <Switch
                    checked={settings.gpt_auto_trading_enabled}
                    onChange={handleSwitchChange}
                    name="gpt_auto_trading_enabled"
                    color="secondary"
                  />
                } 
                label="GPT 기반 자동 매매"
              />
            </FormGroup>
          </Grid>
          
          <Grid item xs={12} md={6}>
            <FormGroup>
              <FormControlLabel 
                control={
                  <Switch
                    checked={settings.day_trading_mode}
                    onChange={handleSwitchChange}
                    name="day_trading_mode"
                    color="primary"
                  />
                } 
                label="단타매매 모드"
              />
              <FormControlLabel 
                control={
                  <Switch
                    checked={settings.swing_trading_mode}
                    onChange={handleSwitchChange}
                    name="swing_trading_mode"
                    color="secondary"
                  />
                } 
                label="스윙매매 모드"
              />
            </FormGroup>
          </Grid>
        </Grid>
        
        <Box sx={{ mt: 3 }}>
          <FormControl fullWidth>
            <InputLabel id="trading-strategy-label">트레이딩 전략</InputLabel>
            <Select
              labelId="trading-strategy-label"
              id="trading-strategy"
              value={settings.trading_strategy}
              label="트레이딩 전략"
              onChange={handleStrategyChange}
            >
              <MenuItem value="conservative">보수적 (Conservative)</MenuItem>
              <MenuItem value="balanced">균형 (Balanced)</MenuItem>
              <MenuItem value="aggressive">공격적 (Aggressive)</MenuItem>
              <MenuItem value="dip_buying">저점매수 (Dip Buying)</MenuItem>
            </Select>
          </FormControl>
        </Box>
      </Paper>
      
      <Paper elevation={2} sx={{ p: 3, mb: 4 }}>
        <Typography variant="h6" gutterBottom>알림 설정</Typography>
        <Divider sx={{ mb: 3 }} />
        
        <FormGroup>
          <FormControlLabel 
            control={
              <Switch
                checked={settings.telegram_enabled}
                onChange={handleSwitchChange}
                name="telegram_enabled"
                color="primary"
              />
            } 
            label="텔레그램 알림"
          />
          <FormControlLabel 
            control={
              <Switch
                checked={settings.kakao_enabled}
                onChange={handleSwitchChange}
                name="kakao_enabled"
                color="secondary"
              />
            } 
            label="카카오톡 알림"
          />
        </FormGroup>
      </Paper>
      
      <Paper elevation={2} sx={{ p: 3, mb: 4 }}>
        <Typography variant="h6" gutterBottom>매매 한도 설정</Typography>
        <Divider sx={{ mb: 3 }} />
        
        <Box sx={{ mb: 4 }}>
          <Typography id="max-position-slider" gutterBottom>
            종목당 최대 포지션 수량: {settings.max_position_per_stock}
          </Typography>
          <Slider
            aria-labelledby="max-position-slider"
            value={settings.max_position_per_stock}
            onChange={handleSliderChange('max_position_per_stock')}
            min={1}
            max={100}
            step={1}
            valueLabelDisplay="auto"
          />
        </Box>
        
        <Box>
          <Typography id="max-amount-slider" gutterBottom>
            1회 최대 매수 금액: {new Intl.NumberFormat('ko-KR', { style: 'currency', currency: 'KRW' }).format(settings.max_amount_per_trade)}
          </Typography>
          <Slider
            aria-labelledby="max-amount-slider"
            value={settings.max_amount_per_trade}
            onChange={handleSliderChange('max_amount_per_trade')}
            min={100000}
            max={10000000}
            step={100000}
            valueLabelDisplay="auto"
            valueLabelFormat={(value) => new Intl.NumberFormat('ko-KR', { style: 'currency', currency: 'KRW', maximumFractionDigits: 0 }).format(value)}
          />
        </Box>
      </Paper>
      
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 3 }}>
        <Button
          variant="contained"
          color="primary"
          startIcon={<SaveIcon />}
          onClick={saveSettings}
          disabled={saving || loading}
        >
          {saving ? '저장 중...' : '설정 저장'}
        </Button>
        
        <Button
          variant="contained"
          color="secondary"
          startIcon={<PlayArrowIcon />}
          onClick={runTradingCycle}
          disabled={saving || loading || !settings.auto_trading_enabled}
        >
          트레이딩 사이클 실행
        </Button>
      </Box>
      
      <Snackbar
        open={notification.open}
        autoHideDuration={6000}
        onClose={closeNotification}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert onClose={closeNotification} severity={notification.severity} sx={{ width: '100%' }}>
          {notification.message}
        </Alert>
      </Snackbar>
    </Container>
  );
};

export default Settings;