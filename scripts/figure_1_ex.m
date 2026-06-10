% ----------------------------------------------------------------------- %
%
% Figure 1 of Archer et al. (2025)
%
% Matlab code shared on Zenodo.
%
% Paper:
% "Wide-swath satellite altimetry unveils global submesoscale ocean
% dynamics" by M. Archer, J. Wang, P. Klein, G. Dibarboure, and L-L Fu.
% Nature 2025.
%
% Requirements:
% --> Matlab: https://www.mathworks.com/products/matlab.html
% --> M_Map: www.eoas.ubc.ca/~rich/map.html
%
% Data links:
% --> SWOT L2: https://doi.org/10.5067/SWOT-SSH-2.0
% --> DUACS: https://doi.org/10.48670/moi-00149
% --> ETOPO1: https://www.ncei.noaa.gov/access/metadata/landing-page/bin/iso?id=gov.noaa.ngdc.mgg.dem:316
%
% ----------------------------------------------------------------------- %

clear;clc

% Lon/Lat limits for Mascarene Plateau
ln = -5; ls = -20; le = 68; lw = 48; % north,south,east,west

%% DATA

% ---------------------------------------------------------------------SWOT 
% SWOT Level 2 - requires quality control
fname = '/path/to/SWOT_L2_LR_SSH_Unsmoothed_514_012_20230508T010922_20230508T020028_PIB0_01.nc';

% RIGHT-HAND SIDE
lon1 = ncread(fname,'/right/longitude');lon1(lon1>180) = lon1(lon1>180)-360;
lat1 = ncread(fname,'/right/latitude');
% Conditional
cswath = 120; % get center of SWOT (250m product)
lonc = lon1(cswath,:); latc = lat1(cswath,:);
indc = find(lonc >= lw & lonc <= le & latc >= ls & latc <= ln);
% Subset
sshr = ncread(fname,'/right/ssh_karin_2',[1 indc(1)],[240 length(indc)]);
lonr = lon1(:,indc);
latr = lat1(:,indc);
mssr = ncread(fname,'/right/mean_sea_surface_cnescls',[1 indc(1)],[240 length(indc)]);
%
timer = ncread(fname,'/right/time',indc(1),length(indc))/60/60/24 + datenum(2000,1,1);
clear lon1 lat1 

% LEFT-HAND SIDE
lon1 = ncread(fname,'/left/longitude');lon1(lon1>180) = lon1(lon1>180)-360;
lat1 = ncread(fname,'/left/latitude');
% Subset
sshl = ncread(fname,'/left/ssh_karin_2',[1 indc(1)],[240 length(indc)]);
lonl = lon1(:,indc);
latl = lat1(:,indc);
mssl = ncread(fname,'/left/mean_sea_surface_cnescls',[1 indc(1)],[240 length(indc)]);
%
timel = ncread(fname,'/left/time',indc(1),length(indc))/60/60/24 + datenum(2000,1,1);
clear lon1 lat1 %lonc latc 

% Remove mean sea surface
sl = sshl - mssl;
sr = sshr - mssr;

% Detrend as ad hoc removal of roll error
% [Cautionary remark: this is sufficient for visualization only, not
% quantitative analysis.]
n = 3;
% LEFT-HAND
sshqc = sl;
sshqc(sshqc > n | sshqc < -n) = NaN;
sshlf = detrend(sshqc','omitnan')'; clear sshqc 
% RIGHT-HAND
sshqc = sr;
sshqc(sshqc > n | sshqc < -n) = NaN;
sshrf = detrend(sshqc','omitnan')'; clear sshqc 
% ---------------------------------------------------------------------SWOT 

% --------------------------------------------------------------------DUACS 
% Time
timeplot = datenum(2023,5,8); % same day as SWOT measurement

% --------------------------------> Find DUACS data to match
avisopath = '/path/to/DUACS/';
afilen = ['nrt_global_allsat_phy_l4_' datestr(timeplot,'YYYYmmDD')];

afilenl = dir([avisopath '/' afilen '*']);
afile = [afilenl.folder '/' afilenl.name];

% Load DUACS
longitude = ncread(afile,'longitude');
latitude = ncread(afile,'latitude');
sla = ncread(afile,'sla');

% Cut DUACS
% [Cautionary remark: this is sufficient for visualization only, not
% quantitative analysis.]
indlo = find(longitude >= 58 & longitude <= 67);
indla = find(latitude >= -20 & latitude <= -5);
slac = sla(indlo,indla);
slacdt = detrend(slac')';
% --------------------------------------------------------------------DUACS 

% -------------------------------------------------------------------ETOPO1
% Using m_etopo1
lont = ncread('/path/to/ETOPO_2022_v1_30s_N90W180_surface.nc','lon');
latt = ncread('/path/to/ETOPO_2022_v1_30s_N90W180_surface.nc','lat');

% Subset to Mascarene
indlon = find(lont >= lw & lont <= le);
indlat = find(latt >= ls & latt <= ln);
%
zt = ncread('/path/to/ETOPO_2022_v1_30s_N90W180_surface.nc','z',[indlon(1) indlat(1)],[length(indlon) length(indlat)]);
%
% -------------------------------------------------------------------ETOPO1

%% PLOTTING
%% (1) ============================================================ Global Inset

figure
m_proj('Satellite','lat',-10,'lon',60,'rot',10);
[CS,CH]=m_etopo2('contourf',[-7000:250:-1000 -500 -200 -100 0 ],'edgecolor','none');
%
m_coast('patch',[0.7 0.7 0.7],'edgecolor','k'); % Using gray color [0 175 0] 
m_grid('linest','none','linewidth',2,'yaxisloc','left','fontsize',20,'fontweight','bold');
set(gcf,'color','w'),
colorbar('Location','SouthOutside')
set(gca,'fontsize',30)
%
m_patch([60.5 60.5; 64 64; 60.5 64; 60.5 64],[-15 -11; -15 -11; -15 -15; -11 -11],'k','linewidth',3);

% Correction for 'pcolor .m'
X = longitude(indlo);
Y = latitude(indla);
%
x = X-.25/2;

%% (2) ============================================================= Main Figure

figure
m_proj('lambert','lon',([60.5 64]), 'lat',([-15 -11]));hold on;
h=m_pcolor(x,Y,slacdt'); shading flat
set(h,'FaceAlpha',0.75);
m_coast('patch',[0.7 0.7 0.7],'edgecolor','k');
m_grid('linest','none','linewidth',2,'yaxisloc','left','fontsize',20,'fontweight','bold');
set(gcf,'color','w'),
colorbar('Location','SouthOutside')
set(gca,'fontsize',30)
%
hold on
    m_contour(lont(indlon),latt(indlat),zt',[-3000 -2000 -1000 -500 -100],'color',[.5 .5 .5]),hold on 
    %
    m_pcolor(lonl,latl,sshlf),shading flat,hold on
    m_pcolor(lonr,latr,sshrf),shading flat,hold on

    caxis([-.4 .4])
    
    m_plot(lonl(5,:),latl(5,:),'k','linewidth',1),hold on
    m_plot(lonl(end-5,:),latl(end-5,:),'k','linewidth',1),hold on
    m_plot(lonr(5,:),latr(5,:),'k','linewidth',1),hold on
    m_plot(lonr(end-5,:),latr(end-5,:),'k','linewidth',1),hold on

%% (3) ================================================================= Zoom in 

figure
    pcolor(lonl,latl,sshlf),shading flat,hold on
    pcolor(lonr,latr,sshrf),shading flat,hold on
    %
    set(gcf,'color','w'),
    colorbar('Location','SouthOutside')
    set(gca,'fontsize',30)  
    Y=get(gca,'ylim');set(gca,'dataaspectratio',[1 cos((Y(2)+Y(1))/2/180*pi) 1])
    caxis([-.4 .4])
    %
    % ZOOM
    ylim([-15 -14.2])
    xlim([63.3 63.85])