'use strict';
document.getElementById('access-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = event.target.querySelector('button');
  button.disabled = true; button.textContent = 'Opening your learning space…';
  document.getElementById('access-error').hidden = true;
  try {
    const response = await fetch('/api/access', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({code: document.getElementById('code').value})});
    document.getElementById('code').value = '';
    const data = await response.json();
    if (!response.ok) throw new Error(data.error?.message || 'Please try again.');
    window.location.assign('/');
  } catch (error) {
    document.getElementById('access-error').hidden = false;
    document.getElementById('access-error').textContent = error instanceof TypeError ? 'The service is temporarily unavailable.' : error.message;
  } finally { button.disabled = false; button.textContent = 'Continue'; }
});
