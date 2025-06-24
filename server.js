// server.js

const express = require('express');
const runMonitor = require('./monitor');

const app = express();
const PORT = process.env.PORT || 3000;

// Root health check
app.get('/', (req, res) => {
  console.log('▶️ Received GET /');
  res.send('Popmart Monitor is running.');
});

// Ping endpoint for UptimeRobot
app.get('/ping', (req, res) => {
  console.log('▶️ Received GET /ping — starting monitor');
  runMonitor()
    .then(() => console.log('✅ Monitor run complete'))
    .catch(err => console.error('❌ Monitor error:', err));
  res.send('OK');
});

app.listen(PORT, () => {
  console.log(`🚀 Server listening on port ${PORT}`);
});
