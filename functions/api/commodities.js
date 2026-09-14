const KEY = 'commodities:v1:latest';
const MARKETS = ['MCX', 'US_COM'];
const date = value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) &&
  Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0,10) === value;

function validHistory(history, kind) {
  if (!history || history.schema_version !== (kind === 'zones' ? 'vt-locked-zones.v1' : `${kind}-history.v1`) ||
      !Array.isArray(history.instrument_columns) || !history.instrument_columns.includes('exchange') ||
      !Array.isArray(history.instruments) || !Array.isArray(history.row_columns) ||
      !Array.isArray(history.periods) || !history.periods.length || history.periods.length > 13) return false;
  const index = history.row_columns.indexOf('instrument_index');
  if (index < 0 || history.instruments.some(row => !Array.isArray(row) || row.length !== history.instrument_columns.length)) return false;
  let previous = '';
  for (const period of history.periods) {
    if (!date(period.date) || period.date <= previous || !Array.isArray(period.rows) ||
        period.rows.some(row => !Array.isArray(row) || row.length !== history.row_columns.length ||
          !Number.isInteger(row[index]) || row[index] < 0 || row[index] >= history.instruments.length)) return false;
    previous = period.date;
  }
  return true;
}

export function validSnapshot(value) {
  if (value?.schema_version !== 'commodities.snapshot.v1' || !Number.isFinite(Date.parse(value.generated_at_utc)) ||
      !/^[a-f0-9]{64}$/.test(value.snapshot_sha256 || '') || !Array.isArray(value.shortlist) || !value.coverage) return false;
  for (const kind of ['ht','vt']) {
    const source = value[kind];
    if (!source || !Array.isArray(source.columns) || !source.markets ||
        source.schema_version !== (kind === 'ht' ? 'tsha-hbcs.snapshot.v1' : 'volume-trend.snapshot.v1')) return false;
    if (Object.keys(source.markets).some(key => !MARKETS.includes(key))) return false;
    const marketIndex = source.columns.indexOf('market'), symbolIndex = source.columns.indexOf('symbol');
    if (marketIndex < 0 || symbolIndex < 0) return false;
    for (const [market, record] of Object.entries(source.markets)) {
      if (!date(record.data_session)) return false;
      for (const timeframe of ['daily','weekly']) {
        const bucket = record.timeframes?.[timeframe];
        if (!bucket || !date(bucket.signal_date) || !Array.isArray(bucket.rows) || bucket.rows.length !== bucket.shortlist_size ||
            !Array.isArray(bucket.appearance_periods) || !bucket.appearance_periods.every(date) ||
            !validHistory(bucket.history, kind)) return false;
        if (bucket.history.periods.at(-1).date !== bucket.signal_date ||
            JSON.stringify(bucket.appearance_periods) !== JSON.stringify(bucket.history.periods.slice(-8).map(period => period.date))) return false;
        if (timeframe === 'weekly' && bucket.history.periods.some(period => new Date(period.date).getUTCDay() !== 1)) return false;
        if (kind === 'vt' && bucket.locked_zones) {
          if (!validHistory(bucket.locked_zones, 'zones')) return false;
          if (timeframe === 'weekly' && bucket.locked_zones.periods.some(period =>
            new Date(period.date).getUTCDay() !== 1 || Date.parse(period.date) + 4 * 86400000 > Date.parse(record.data_session))) return false;
        }
        if (bucket.rows.some(row => !Array.isArray(row) || row.length !== source.columns.length || row[marketIndex] !== market ||
            typeof bucket.appearance_bits?.[row[symbolIndex]] !== 'string' ||
            !/^[01]+$/.test(bucket.appearance_bits[row[symbolIndex]]) ||
            bucket.appearance_bits[row[symbolIndex]].length !== bucket.appearance_periods.length)) return false;
      }
    }
  }
  return MARKETS.every(market => Boolean(value.ht.markets[market]) === Boolean(value.vt.markets[market]) &&
    (!value.ht.markets[market] || ['daily','weekly'].every(timeframe =>
      value.ht.markets[market].timeframes[timeframe].signal_date === value.vt.markets[market].timeframes[timeframe].signal_date))) &&
    value.shortlist.every(row => {
      const bucket = value.ht.markets[row.market]?.timeframes?.[row.timeframe];
      const bits = row.appearance_bits;
      return MARKETS.includes(row.market) && ['daily','weekly'].includes(row.timeframe) &&
        row.signal_date === bucket?.signal_date && typeof bits === 'string' && /^[01]+1$/.test(bits) &&
        (bits.slice(-3).split('1').length - 1 >= 2 || bits.slice(-5).split('1').length - 1 >= 3);
    });
}

export async function onRequestGet({env}) {
  const json = (body, status = 200) => Response.json({schema_version:'commodities.api.v1', ...body},
    {status, headers:{'cache-control':status === 200 ? 'private, max-age=300' : 'no-store'}});
  if (!env.SCANLINKS) return json({error:'Commodity snapshot store unavailable'}, 503);
  try {
    const snapshot = await env.SCANLINKS.get(KEY, {type:'json', cacheTtl:300});
    if (!snapshot) return json({error:'Commodity history is not available yet'}, 503);
    if (!validSnapshot(snapshot)) return json({error:'Commodity snapshot failed validation'}, 503);
    return json({snapshot});
  } catch {
    return json({error:'Commodity snapshot read failed'}, 503);
  }
}
