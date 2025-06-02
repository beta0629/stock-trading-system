import React from 'react';
import { 
  Drawer, List, ListItem, ListItemIcon, ListItemText, ListItemButton, 
  Divider, Box, Typography, Collapse 
} from '@mui/material';
import { NavLink } from 'react-router-dom';
import DashboardIcon from '@mui/icons-material/Dashboard';
import ShowChartIcon from '@mui/icons-material/ShowChart';
import AccountBalanceIcon from '@mui/icons-material/AccountBalance';
import SettingsIcon from '@mui/icons-material/Settings';
import BarChartIcon from '@mui/icons-material/BarChart';
import ExpandLess from '@mui/icons-material/ExpandLess';
import ExpandMore from '@mui/icons-material/ExpandMore';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import TrendingDownIcon from '@mui/icons-material/TrendingDown';

const Sidebar = ({ open, onClose }) => {
  const drawerWidth = open ? 240 : 60;
  
  const [stocksOpen, setStocksOpen] = React.useState(false);
  
  const handleStocksClick = () => {
    if (!open) return;
    setStocksOpen(!stocksOpen);
  };

  return (
    <Drawer
      variant="permanent"
      anchor="left"
      open={open}
      sx={{
        width: drawerWidth,
        flexShrink: 0,
        '& .MuiDrawer-paper': {
          width: drawerWidth,
          boxSizing: 'border-box',
          transition: 'width 0.2s',
          whiteSpace: 'nowrap',
          overflowX: 'hidden'
        }
      }}
    >
      <Box sx={{ height: '64px', display: 'flex', alignItems: 'center', px: 2 }}>
        {open && (
          <Typography variant="h6" noWrap component="div">
            메뉴
          </Typography>
        )}
      </Box>
      <Divider />
      
      <List>
        <ListItem disablePadding>
          <ListItemButton 
            component={NavLink} 
            to="/dashboard"
            sx={{ 
              minHeight: 48,
              justifyContent: open ? 'initial' : 'center',
              px: 2.5
            }}
          >
            <ListItemIcon
              sx={{
                minWidth: 0,
                mr: open ? 3 : 'auto',
                justifyContent: 'center',
              }}
            >
              <DashboardIcon />
            </ListItemIcon>
            {open && <ListItemText primary="대시보드" />}
          </ListItemButton>
        </ListItem>
        
        <ListItem disablePadding>
          <ListItemButton 
            onClick={handleStocksClick}
            sx={{ 
              minHeight: 48,
              justifyContent: open ? 'initial' : 'center',
              px: 2.5
            }}
          >
            <ListItemIcon
              sx={{
                minWidth: 0,
                mr: open ? 3 : 'auto',
                justifyContent: 'center',
              }}
            >
              <ShowChartIcon />
            </ListItemIcon>
            {open && (
              <>
                <ListItemText primary="주식" />
                {stocksOpen ? <ExpandLess /> : <ExpandMore />}
              </>
            )}
          </ListItemButton>
        </ListItem>
        
        <Collapse in={open && stocksOpen} timeout="auto" unmountOnExit>
          <List component="div" disablePadding>
            <ListItemButton 
              component={NavLink}
              to="/stocks?market=KR"
              sx={{ pl: 4 }}
            >
              <ListItemIcon>
                <TrendingUpIcon />
              </ListItemIcon>
              <ListItemText primary="한국 주식" />
            </ListItemButton>
            <ListItemButton 
              component={NavLink}
              to="/stocks?market=US"
              sx={{ pl: 4 }}
            >
              <ListItemIcon>
                <TrendingDownIcon />
              </ListItemIcon>
              <ListItemText primary="미국 주식" />
            </ListItemButton>
          </List>
        </Collapse>
        
        <ListItem disablePadding>
          <ListItemButton 
            component={NavLink} 
            to="/portfolio"
            sx={{ 
              minHeight: 48,
              justifyContent: open ? 'initial' : 'center',
              px: 2.5
            }}
          >
            <ListItemIcon
              sx={{
                minWidth: 0,
                mr: open ? 3 : 'auto',
                justifyContent: 'center',
              }}
            >
              <AccountBalanceIcon />
            </ListItemIcon>
            {open && <ListItemText primary="포트폴리오" />}
          </ListItemButton>
        </ListItem>
        
        <ListItem disablePadding>
          <ListItemButton 
            component={NavLink} 
            to="/reports"
            sx={{ 
              minHeight: 48,
              justifyContent: open ? 'initial' : 'center',
              px: 2.5
            }}
          >
            <ListItemIcon
              sx={{
                minWidth: 0,
                mr: open ? 3 : 'auto',
                justifyContent: 'center',
              }}
            >
              <BarChartIcon />
            </ListItemIcon>
            {open && <ListItemText primary="리포트" />}
          </ListItemButton>
        </ListItem>
      </List>
      
      <Divider />
      
      <List>
        <ListItem disablePadding>
          <ListItemButton 
            component={NavLink} 
            to="/settings"
            sx={{ 
              minHeight: 48,
              justifyContent: open ? 'initial' : 'center',
              px: 2.5
            }}
          >
            <ListItemIcon
              sx={{
                minWidth: 0,
                mr: open ? 3 : 'auto',
                justifyContent: 'center',
              }}
            >
              <SettingsIcon />
            </ListItemIcon>
            {open && <ListItemText primary="설정" />}
          </ListItemButton>
        </ListItem>
      </List>
    </Drawer>
  );
};

export default Sidebar;