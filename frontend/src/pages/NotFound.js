import React from 'react';
import { Container, Typography, Button, Box, Paper } from '@mui/material';
import { Link as RouterLink } from 'react-router-dom';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';
import HomeIcon from '@mui/icons-material/Home';

const NotFound = () => {
  return (
    <Container maxWidth="md" sx={{ py: 8 }}>
      <Paper elevation={3} sx={{ p: 4, textAlign: 'center' }}>
        <Box sx={{ mb: 2 }}>
          <ErrorOutlineIcon sx={{ fontSize: 80, color: 'error.main' }} />
        </Box>
        <Typography variant="h3" component="h1" gutterBottom>
          404 - 페이지를 찾을 수 없습니다
        </Typography>
        <Typography variant="body1" color="text.secondary" paragraph>
          요청하신 페이지를 찾을 수 없습니다. URL을 확인하시거나 아래 버튼을 클릭하여 홈페이지로 이동하세요.
        </Typography>
        <Button 
          variant="contained" 
          color="primary" 
          component={RouterLink} 
          to="/"
          startIcon={<HomeIcon />}
          sx={{ mt: 2 }}
        >
          홈페이지로 돌아가기
        </Button>
      </Paper>
    </Container>
  );
};

export default NotFound;