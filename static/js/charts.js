function renderPieChart(canvasId, labels, values) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) {
    return;
  }

  new Chart(ctx, {
    type: 'pie',
    data: {
      labels: labels,
      datasets: [{
        data: values,
        backgroundColor: ['#4e79a7', '#f28e2b', '#59a14f', '#e15759']
      }]
    },
    options: {
      responsive: true,
      plugins: {
        legend: { position: 'bottom' }
      }
    }
  });
}

function renderBarChart(canvasId, labels, values) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) {
    return;
  }

  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: 'Total Amount',
        data: values,
        backgroundColor: '#76b7b2'
      }]
    },
    options: {
      responsive: true,
      scales: {
        y: {
          beginAtZero: true
        }
      }
    }
  });
}
