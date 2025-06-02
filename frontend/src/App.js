import React, { useState, useEffect } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import Box from '@mui/material/Box';

// 페이지 컴포넌트
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import StockList from './pages/StockList';
import StockDetail from './pages/StockDetail';
import Portfolio from './pages/Portfolio';
import Settings from './pages/Settings';
import NotFound from './pages/NotFound';

// 컴포넌트
import Header from './components/Header';
import Sidebar from './components/Sidebar';

// 서비스 및 유틸리티
import { authService } from './services/authService';

function App() {
  const [darkMode, setDarkMode] = useState(localStorage.getItem('darkMode') === 'true');
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [user, setUser] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  // 테마 설정
  const theme = createTheme({
    palette: {
      mode: darkMode ? 'dark' : 'light',
      primary: {
        main: '#2196f3',
      },
      secondary: {
        main: '#f50057',
      },
      background: {
        default: darkMode ? '#121212' : '#f5f5f5',
        paper: darkMode ? '#1e1e1e' : '#ffffff',
      },
    },
  });

  // 다크 모드 토글 함수
  const toggleDarkMode = () => {
    setDarkMode(!darkMode);
    localStorage.setItem('darkMode', !darkMode);
  };

  // 사이드바 토글 함수
  const toggleSidebar = () => {
    setSidebarOpen(!sidebarOpen);
  };

  // 인증 상태 확인
  useEffect(() => {
    const checkAuth = async () => {
      const isLoggedIn = await authService.isAuthenticated();
      setIsAuthenticated(isLoggedIn);
      
      if (isLoggedIn) {
        const userData = await authService.getCurrentUser();
        setUser(userData);
      }
    };

    checkAuth();
  }, []);

  // 로그아웃 처리
  const handleLogout = () => {
    authService.logout();
    setIsAuthenticated(false);
    setUser(null);
    window.location.href = '/login';
  };

  // 인증이 필요한 라우트를 위한 래퍼 컴포넌트
  const ProtectedRoute = ({ children }) => {
    if (!isAuthenticated) {
      return <Navigate to="/login" replace />;
    }
    return children;
  };

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      {isAuthenticated && (
        <Header 
          user={user} 
          onLogout={handleLogout}
          toggleDarkMode={toggleDarkMode}
          darkMode={darkMode}
          toggleSidebar={toggleSidebar}
          sidebarOpen={sidebarOpen}
        />
      )}
      
      <Box sx={{ 
        display: 'flex', 
        width: '100%', 
        height: '100vh',
        paddingTop: isAuthenticated ? '64px' : 0, // 헤더 높이만큼 패딩 추가
      }}>
        {isAuthenticated && (
          <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
        )}

        <Box
          component="main"
          sx={{
            flexGrow: 1,
            p: 3,
            width: '100%',
            overflowX: 'hidden'
          }}
        >
          <Routes>
            <Route path="/login" element={
              isAuthenticated ? <Navigate to="/dashboard" replace /> : <Login onLogin={() => setIsAuthenticated(true)} />
            } />
            
            <Route path="/dashboard" element={
              <ProtectedRoute>
                <Dashboard />
              </ProtectedRoute>
            } />
            
            <Route path="/stocks" element={
              <ProtectedRoute>
                <StockList />
              </ProtectedRoute>
            } />
            
            <Route path="/stocks/:market/:symbol" element={
              <ProtectedRoute>
                <StockDetail />
              </ProtectedRoute>
            } />
            
            <Route path="/portfolio" element={
              <ProtectedRoute>
                <Portfolio />
              </ProtectedRoute>
            } />
            
            <Route path="/settings" element={
              <ProtectedRoute>
                <Settings />
              </ProtectedRoute>
            } />
            
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Box>
      </Box>
    </ThemeProvider>
  );
}

export default App;