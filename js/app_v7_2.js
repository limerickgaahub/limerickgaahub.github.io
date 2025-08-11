console.log('App v7.2 loaded');
// This is a placeholder JS - full dropdown, table, and fixtures logic to be implemented.
fetch('data/hurling_2025.json')
  .then(r => r.json())
  .then(data => console.log('Loaded fixtures:', data.length))
  .catch(err => console.error('Error loading JSON', err));
