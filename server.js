// server.js

const express = require('express');
const runMonitor = require('./monitor');

const app = express();
const PORT = process.env.PORT || 3000;

app.get('/ping', (req, res) => {
  // fire-and-forget the monitor
  runMonitor()
    .catch(err => console.error('Monitor error:', err));
  // immediately return OK
  res.status(200).send('OK');
});

app.get('/', (req, res) => {
  res.send('Popmart Monitor is running.');
});

app.listen(PORT, () => {
  console.log(`Server listening on port ${PORT}`);
});
