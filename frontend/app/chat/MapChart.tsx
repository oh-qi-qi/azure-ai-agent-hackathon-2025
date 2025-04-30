import React, { memo, useState } from 'react';
import { ZoomableGroup, ComposableMap, Geographies, Geography, Graticule, Sphere } from 'react-simple-maps';
import countries from '@/app/dashboard/countries.json';
import '@/app/dashboard/styles.css';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';

const getLikelihoodColor = (value: number) => {
  // Scale of 0-5
  if (value <= 1) return '#A8E6CF'; // Bright green for very low risk
  if (value <= 2) return '#DCE775'; // Light green-yellow
  if (value <= 3) return '#FFC107'; // Yellow for medium risk
  if (value <= 4) return 'rgb(255, 126, 86)'; // Orange
  return '#F44336'; // Red for high risk
};

const getLikelihoodTextColor = (value: number) => {
  if (value <= 1) return '#0B3D2E'; // Deep forest green
  if (value <= 2) return '#4A4A00'; // Muted olive-brown
  if (value <= 3) return '#B25B00'; // Burnt amber
  if (value <= 4) return '#8B2500'; // Deep rust orange
  return '#7F0000'; // Dark crimson red
};

const MapChart = ({ setTooltipContent, breakdown }) => {
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [selectedCountry, setSelectedCountry] = useState(null);

  const parseBreakdown = (data) => {
    try {
      return JSON.parse(data);
    } catch (e) {
      return [];
    }
  };

  console.log(breakdown);
  return (
    <div className="w-[700px] h-[500px]">
      <p className="text-md font-semibold mb-4">Country Risk Analysis</p>

      <div className="flex items-center gap-4 mt-4 text-sm">
        <span className="font-semibold">Risk Level:</span>
        {[1, 2, 3, 4, 5].map((value) => (
          <div key={value} className="flex items-center gap-1">
            <div className="w-4 h-4 rounded" style={{ backgroundColor: getLikelihoodColor(value) }} />
            <span>{value}</span>
          </div>
        ))}
      </div>

      <ComposableMap
        projectionConfig={{
          rotate: [-10, 0, 0],
          scale: 147,
        }}
      >
        <Sphere stroke="#E4E5E6" strokeWidth={0.5} />
        <Graticule stroke="#E4E5E6" strokeWidth={0.5} />
        <Geographies geography={countries}>
          {({ geographies }) =>
            geographies.map((geo) => {
              const countryData = breakdown.find((item) => item.country === geo.properties.name);
              const likelihood = countryData ? parseInt(countryData.average_risk) : 0;

              return (
                <Geography
                  key={geo.rsmKey}
                  geography={geo}
                  data-tooltip-id="country-tooltip"
                  className="cursor-pointer"
                  onMouseEnter={() => {
                    const tooltipText = countryData
                      ? `${geo.properties.name} (Risk: ${likelihood}/5)`
                      : geo.properties.name;
                    setTooltipContent(tooltipText);
                  }}
                  onMouseLeave={() => {
                    setTooltipContent('');
                  }}
                  onClick={() => {
                    if (countryData) {
                      setSelectedCountry(countryData);
                      setIsDialogOpen(true);
                    }
                  }}
                  style={{
                    default: {
                      fill: countryData ? getLikelihoodColor(likelihood) : 'rgb(193, 203, 207)',
                      outline: 'none',
                      cursor: countryData ? 'pointer' : 'default',
                    },
                    hover: {
                      fill: '#3498DB',
                      outline: 'none',
                    },
                    pressed: {
                      fill: countryData ? getLikelihoodColor(likelihood + 1) : '#3498DB',
                      outline: 'none',
                    },
                  }}
                />
              );
            })
          }
        </Geographies>
      </ComposableMap>

      <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
        <DialogContent className="!max-w-[900px] !w-11/12 sm:!max-w-[800px]">
          <DialogHeader>
            <DialogTitle>{selectedCountry?.country}</DialogTitle>
          </DialogHeader>
          {selectedCountry && (
            <ScrollArea className="max-h-[600px] pr-6">
              <div className="mb-2">
                <Badge
                  className="text-sm font-bold mb-4"
                  style={{
                    backgroundColor: getLikelihoodColor(parseInt(selectedCountry.average_risk)),
                    color: getLikelihoodTextColor(parseInt(selectedCountry.average_risk)),
                  }}
                >
                  Average Risk: {selectedCountry.average_risk}
                </Badge>
                <p className="text-sm text-muted-foreground">
                  Date: {new Date(selectedCountry.datetime_stamp).toLocaleDateString()}
                </p>
              </div>
              {parseBreakdown(selectedCountry.breakdown).map((item, index) => (
                <div key={index} className="mb-6">
                  <p className="text-md font-semibold mb-4">Risk Breakdown</p>
                  <Table className="border">
                    <TableBody>
                      <TableRow>
                        <TableHead className="w-[150px]">Description</TableHead>
                        <TableCell>{item.description}</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableHead>Summary</TableHead>
                        <TableCell>{item.summary}</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableHead>Likelihood</TableHead>
                        <TableCell>
                          <span
                            className="px-3 py-1 rounded-full"
                            style={{
                              backgroundColor: getLikelihoodColor(parseInt(item.likelihood)),
                              color: getLikelihoodTextColor(parseInt(item.likelihood)),
                              fontWeight: 'bold',
                            }}
                          >
                            {item.likelihood}
                          </span>
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableHead>Reasoning</TableHead>
                        <TableCell>{item.likelihood_reasoning}</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableHead>Source</TableHead>
                        <TableCell>
                          <a
                            href={item.source_url.replace('[Link]', '').replace('(', '').replace(')', '')}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-blue-600 hover:underline"
                          >
                            {item.source}
                          </a>
                        </TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
                </div>
              ))}
            </ScrollArea>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default memo(MapChart);
