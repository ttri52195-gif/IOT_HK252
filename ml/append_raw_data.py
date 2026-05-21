"""Append 3000 more synthetic samples to raw_data.csv with similar distribution."""
import csv
from pathlib import Path
from datetime import datetime
import numpy as np

# Parameters
num_samples = 3000
temp_min, temp_max = -20, 100
hum_min, hum_max = 0, 100

# Generate data: temperature uniformly distributed from -20 to 100
temps = np.linspace(temp_min, temp_max, num_samples)
# Humidity randomly distributed 0-100
humids = np.random.uniform(hum_min, hum_max, num_samples)

# Timestamp for all new samples
timestamp = datetime.utcnow().isoformat() + 'Z'

# Append to raw_data.csv
output = Path('raw_data.csv')
if not output.exists():
    print(f'Error: {output} not found!')
    exit(1)

with output.open('a', encoding='utf-8-sig', newline='') as f:
    writer = csv.writer(f)
    for t, h in zip(temps, humids):
        raw_line = f'T={t:.4f} H={h:.4f}'
        writer.writerow([timestamp, f'{t:.4f}', f'{h:.4f}', raw_line])

print(f'Appended {num_samples} samples to {output}')
print(f'Temp range: {temps.min():.2f} to {temps.max():.2f}')
print(f'Hum range: {humids.min():.2f} to {humids.max():.2f}')

# Show file stats
total_lines = sum(1 for _ in output.open()) - 1  # exclude header
print(f'Total samples in file: {total_lines}')
print(f'File size: {output.stat().st_size / 1024:.2f} KB')
