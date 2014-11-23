import logging
import time

import wx
import wx.lib.wxcairo
import cairo

from chisualizer.visualizers.VisualizerBase import AbstractVisualizer
from chisualizer.visualizers.Theme import LightTheme, DarkTheme

class ChisualizerFrame(wx.Frame):
  def __init__(self, parent, title, api, desc):
    wx.Frame.__init__(self, parent, title=title, size=(1280,800))
    self.canvas = ChisualizerPanel(self, api, desc)
    self.Show()

class ChisualizerPanel(wx.Panel):
  def __init__(self, parent, api, desc):
    wx.Panel.__init__(self, parent, style=wx.BORDER_SIMPLE)
    self.Bind(wx.EVT_PAINT, self.OnPaint)
    self.Bind(wx.EVT_SIZE, self.OnSize)
    self.Bind(wx.EVT_CHAR, self.OnChar)
    self.Bind(wx.EVT_MOUSEWHEEL, self.OnMouseWheel)
    self.Bind(wx.EVT_MOTION, self.OnMouseMotion)
    self.Bind(wx.EVT_RIGHT_UP, self.OnMouseRight)
    self.Bind(wx.EVT_LEFT_DCLICK, self.OnMouseLeftDClick)
    
    self.api = api
    self.desc = desc
    
    self.scale = 1
    self.center = (0, 0)  # center of visualization, in visualizer coords
    self.mouse_vis = (0, 0)   # mouse position, in visualizer coords
    
    self.need_visualizer_refresh = False
    self.elements = []
    
    self.cycle = 0
    self.snapshots = []

  def OnChar(self, evt):
    char = evt.GetKeyCode()
    if char == ord('r'):
      logging.info("Reset circuit")
      self.api.reset(1)
      self.cycle = 0
      self.snapshots = []
      self.need_visualizer_refresh = True
      
    elif char == wx.WXK_RIGHT:
      logging.info("Clock circuit")
      self.api.snapshot_save(str(self.cycle))
      self.snapshots.append(self.cycle)
      self.cycle += self.api.clock(1)
      self.need_visualizer_refresh = True
      
    elif char == wx.WXK_LEFT:
      logging.info("Revert circuit")
      if self.snapshots:
        self.cycle = self.snapshots.pop()
        self.api.snapshot_restore(str(self.cycle))
        self.need_visualizer_refresh = True
    
    elif char == ord('s'):
      cur_val = -1
      dlg = wx.TextEntryDialog(None, 'Step', 'Cycles to step', "1")
      while cur_val < 1:
        ret = dlg.ShowModal()
        if ret != wx.ID_OK:
          return
        dlg_val = dlg.GetValue()
        try:
          cur_val = int(dlg_val)
        except:
          pass
        
      logging.info("Clock circuit (%i cycles)" % cur_val)
        
      self.api.snapshot_save(str(self.cycle))
      self.snapshots.append(self.cycle)
      self.cycle += self.api.clock(cur_val)
      self.need_visualizer_refresh = True
      
    elif char == ord('p'):
      self.save_svg("%s_%i.svg" % ("chisualizer", self.cycle))
    
    elif char == ord('q'):
      logging.info("Exit")
      sys.exit()
      
    self.Refresh()

  def OnSize(self, evt):
    self.need_visualizer_refresh = True
    self.Refresh()

  def OnMouseWheel(self, evt):
    delta = evt.GetWheelRotation() / evt.GetWheelDelta()
    scale_factor = 1.2 ** delta
    self.scale = self.scale * scale_factor
    self.center = (-self.mouse_vis[0] + (self.mouse_vis[0] + self.center[0])/scale_factor,
                   -self.mouse_vis[1] + (self.mouse_vis[1] + self.center[1])/scale_factor)
    self.need_visualizer_refresh = True
    self.Refresh()

  def OnMouseMotion(self, evt):
    self.mouse_vis = self.device_to_visualizer_coordinates((evt.GetX(), evt.GetY()))
    self.Refresh()

  def OnMouseRight(self, evt):
    x, y = self.device_to_visualizer_coordinates(evt.GetPosition())
    elements = self.get_mouseover_elements(x, y)
    elements = sorted(elements, key = lambda element: element[0], reverse=True)
    
    menu = wx.Menu()
    populated = False
    for element in elements:
      assert isinstance(element[1], AbstractVisualizer)
      this_populated = element[1].wx_popupmenu_populate(menu)
      populated = populated or this_populated
    if populated:
      self.PopupMenu(menu, evt.GetPosition())
    menu.Destroy()
    
    self.need_visualizer_refresh = True
    self.Refresh()
    
  def OnMouseLeftDClick(self, evt):
    x, y = self.device_to_visualizer_coordinates(evt.GetPosition())
    elements = self.get_mouseover_elements(x, y)
    if not elements:
      return
    elements = sorted(elements, key = lambda element: element[0], reverse=True)

    assert isinstance(elements[0][1], AbstractVisualizer)
    elements[0][1].wx_defaultaction()
        
    self.need_visualizer_refresh = True
    self.Refresh()
    
  def OnPaint(self, evt):
    dc = wx.PaintDC(self)
    width, height = self.GetClientSize()
    dc.Blit(0, 0, width, height, 
            self.get_visualizer_dc(self.GetClientSize()), 
            0, 0)

    # Per-frame elements
    cr = wx.lib.wxcairo.ContextFromDC(dc)
    cr.set_source_rgba(*self.desc.get_theme().default_color())
    cr.select_font_face('Mono',
                        cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    cr.set_font_size(10)
    cr.move_to(0, height - 50)
    cr.show_text("Center %.1f, %.1f; Scale: %.2f" % (self.center[0], self.center[1], self.scale))
    cr.move_to(0, height - 40)
    cr.show_text("Mouse: %.1f, %.1f" % self.mouse_vis)
    cr.move_to(0, height - 30)
    elements = self.get_mouseover_elements(*self.mouse_vis)
    elements = map(lambda element: element[1].path, elements)
    cr.show_text(str(elements))

  def device_to_visualizer_coordinates(self, pos):
    x, y = pos
    width, height = self.GetClientSize()
    x = x - width / 2
    y = y - height / 2
    x = x / self.scale
    y = y / self.scale
    x = x - self.center[0]
    y = y - self.center[1]
    return (x, y) 

  def get_mouseover_elements(self, x, y):
    elements = []
    for (depth, rect, visualizer) in self.elements:
      if rect.contains(x, y):
        elements.append((depth, visualizer))
    return elements

  def get_visualizer_dc(self, size):
    if self.need_visualizer_refresh:
      self.desc.set_theme(DarkTheme())
      
      width, height = size
      dc = wx.MemoryDC(wx.EmptyBitmap(width, height))
      cr = wx.lib.wxcairo.ContextFromDC(dc)
    
      cr.set_source_rgba(*self.desc.get_theme().background_color())
      cr.rectangle(0, 0, width, height)
      cr.fill()
    
      cr.translate(0.5, 0.5)
      cr.save()
      cr.translate(width/2, height/2)
      cr.scale(self.scale, self.scale)
      cr.translate(*self.center)
      
      timer_draw = time.time()
      self.draw_visualizer(cr)
      timer_draw = time.time() - timer_draw

      cr.restore()
      
      cr.set_source_rgba(*self.desc.get_theme().default_color())
      cr.select_font_face('Mono',
                          cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
      cr.set_font_size(10)
      cr.move_to(0, height - 15)
      cr.show_text("Cycle %i, render: %.2f ms" %
                   (self.cycle, timer_draw*1000))
      cr.move_to(0, height - 5)
      cr.show_text("(<-) back one cycle, (->) forward one cycle, (s) variable cycle step, (r) cycle in reset, (mousewheel) zoom, (p) save to SVG")
      
      self.visualizer_dc = dc
      
    self.need_visualizer_refresh = False
    return self.visualizer_dc

  def draw_visualizer(self, cr):
    timer_update = time.time()
    self.desc.update()
    timer_update = time.time() - timer_update
    
    timer_lay = time.time()
    layout = self.desc.layout_cairo(cr).centerd_origin()
    timer_lay = time.time() - timer_lay
    
    timer_draw = time.time()
    self.elements = self.desc.draw_cairo(cr, layout)
    timer_draw = time.time() - timer_draw
    
    logging.debug("draw_visualizer: layout time: %.2f ms, draw time: %.2f ms" %
                 (timer_lay*1000, timer_draw*1000))
    
  def save_svg(self, filename):
    # TODO: refactor to avoid calling desc.layout here
    self.desc.set_theme(LightTheme())
      
    f = file(filename, 'w')
    surface_test = cairo.SVGSurface(f, 1, 1)  # dummy surface to get layout size
    # TODO make cross platform, 
    cr_test = cairo.Context(surface_test)
    self.desc.update()
    layout = self.desc.layout_cairo(cr_test)
    surface_test.finish()
    
    f = file(filename, 'w')
    surface = cairo.SVGSurface(f, layout.width()+2, layout.height()+2)
    cr = cairo.Context(surface)
    
    cr.set_source_rgba(*self.desc.get_theme().background_color())
    cr.rectangle(0, 0, layout.width()+2, layout.height()+2)
    cr.fill()
    
    cr.translate(1, 1)
    cr.save()
    self.desc.draw_cairo(cr, layout)
    
    surface.finish()
    f.close()
    
    logging.info("Rendered visualizer to SVG '%s'" % filename)
