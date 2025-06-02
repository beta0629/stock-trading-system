import React, { useState } from 'react';
import { Box, Container, Typography, TextField, Button, Paper, Alert } from '@mui/material';
import { authService } from '../services/authService';

const Login = ({ onLogin }) => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const success = await authService.login(username, password);
      if (success) {
        onLogin();
      } else {
        setError('로그인에 실패했습니다. 사용자 이름과 비밀번호를 확인해주세요.');
      }
    } catch (err) {
      setError(err.response?.data?.detail || '로그인 중 오류가 발생했습니다.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Container maxWidth="sm">
      <Box sx={{ 
        mt: 8, 
        display: 'flex', 
        flexDirection: 'column', 
        alignItems: 'center' 
      }}>
        <Paper elevation={3} sx={{ p: 4, width: '100%' }}>
          <Typography component="h1" variant="h5" align="center" gutterBottom>
            주식 트레이딩 시스템
          </Typography>
          
          <Typography component="h2" variant="h6" align="center" sx={{ mb: 3, color: 'text.secondary' }}>
            로그인
          </Typography>

          {error && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {error}
            </Alert>
          )}

          <Box component="form" onSubmit={handleLogin} sx={{ mt: 1 }}>
            <TextField
              margin="normal"
              required
              fullWidth
              id="username"
              label="사용자 이름"
              name="username"
              autoComplete="username"
              autoFocus
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
            
            <TextField
              margin="normal"
              required
              fullWidth
              name="password"
              label="비밀번호"
              type="password"
              id="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />

            <Button
              type="submit"
              fullWidth
              variant="contained"
              sx={{ mt: 3, mb: 2 }}
              disabled={loading}
            >
              {loading ? '로그인 중...' : '로그인'}
            </Button>
          </Box>
        </Paper>
      </Box>
    </Container>
  );
};

export default Login;