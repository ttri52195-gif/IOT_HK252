"""Generate synthetic raw data with specified temperature and humidity distributions."""
import csv
from pathlib import Path
import numpy as np

# Parameters
num_samples = 2000
temp_min, temp_max = -20, 100
hum_min, hum_max = 0, 100

# Generate data: temperature uniformly distributed from -20 to 100
temps = np.linspace(temp_min, temp_max, num_samples)
# Humidity randomly distributed 0-100
humids = np.random.uniform(hum_min, hum_max, num_samples)

# Create CSV in ml folder
output = Path('raw_data.csv')
with output.open('w', encoding='utf-8-sig', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['temperature', 'humidity'])
    for t, h in zip(temps, humids):
        writer.writerow([f'{t:.4f}', f'{h:.4f}'])

print(f'Created {num_samples} samples in {output}')
print(f'Temp range: {temps.min():.2f} to {temps.max():.2f}')
print(f'Temp step: {(temp_max - temp_min) / (num_samples - 1):.4f}')
print(f'Hum range: {humids.min():.2f} to {humids.max():.2f}')
print(f'File size: {output.stat().st_size} bytes')
