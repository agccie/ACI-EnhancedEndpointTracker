/**
 * generic table used by app that supports variable columns and configurable displays per row. Also,
 * allows for API based sortable values and paging.
 * requirement to change the dataset and formatting on demand.
 */

function gHeader(args) {
    var self = this;
    // make everything observable for simplicity
    self.name = ko.observable(("name" in args)? args.name : "" )
    self.title = ko.observable(("title" in args)? args.title : self.name())
    self.sortable = ko.observable(("sortable" in args)? args.sortable : true)
    self.sorted = ko.observable(("sorted" in args)? args.sorted : false)
    self.sort_direction = ko.observable("")
    self.width = ko.observable(("width" in args)? args.width:"")
    //list of gCtrl objects
    self.control = ko.observableArray(("control" in args)? args.control : [])

    self.get_css = ko.computed(function(){
        if(self.sortable()){ return "sortable"}
        return ""
    })
    self.get_sort_css = ko.computed(function(){
        if(self.sortable() && self.sorted()){
            if(self.sort_direction()=="asc"){
                return "sort-indicator icon-chevron-down"
            }else{
                return "sort-indicator icon-chevron-up"
            }
        }
        return ""
    })
}

function gCtrl(args){
    var self = this
    self.click = ("click" in args)? args.click : function(data){}
    self.icon = ko.observable(("icon" in args)? args.icon : "icon-check")
    self.icon_status = ko.observable(("status" in args)? args.status : "")
    self.balloon = ko.observable(("tip" in args)? args.tip : "click")
    self.balloon_pos = ko.observable(("balloon_pos" in args)? args.balloon_pos : "up")
    self.btn_status = ko.computed(function(){
        if(self.icon_status().length>0){
            return "btn--"+self.icon_status()
        }
        return ""
    })
}


function gRow(data){
    var self = this;
    self.data = data;

    //get value of data attribute
    self.get_attribute = function(attr){
        if(self.data.hasOwnProperty(attr)){
            if(ko.isObservable(self.data[attr])){
                return self.data[attr]()
            }else{
                return self.data[attr]
            }
        }
        return ""
    }
    // data object can have 'formatter' object and if attribute name in formatter than return that
    // value, else return raw text
    self.get_attribute_html = function(attr){
        var text = self.get_attribute(attr)
        if(self.data.hasOwnProperty("formatter")){
            return self.data.formatter(attr, text)
        }
        return text
    }
}

function gTable() {
    var self = this;
    self.isLoading = ko.observable(false)
    self.headers = ko.observableArray()
    self.rows = ko.observableArray()
    self.server_paging = ko.observable(true)
    self.page = ko.observable(0)
    self.page_size = ko.observable(25)
    self.refresh_enabled = ko.observable(true)
    self.custom_refresh = null;
    self.display_no_data = ko.observable(true)
    self.no_data_message = ko.observable("No data to display")
    self.title = ko.observable("")
    self.url = ko.observable("")

    // re-init table to defaults
    self.init = function(){
        self.isLoading(false)
        self.headers([])
        self.rows([])
        self.server_paging(true)
        self.page(0)
        self.refresh_enabled(true)
        self.custom_refresh = null
        self.display_no_data(true)
        self.no_data_message("No data to display")
        self.title("")
        self.url("")
    }

    //get just results for current page, (client side paging only)
    self.get_paged_rows = ko.computed(function(){
        if(self.server_paging()){
            return self.rows()
        }
        if(self.page()>=0 && self.page_size()>=0){
            var start = (self.page())*self.page_size()
            var end = (self.page()+1)*self.page_size()
            return self.rows().slice(start, end)
        }
        return []
    })

    // when sortable header is clicked, update which column is sorted and refresh data
    self.toggle_sort = function(hdr){
        //ignore clicks on non-sortable columns
        if(!hdr.sortable()){ return }
        if(hdr.sorted()){
            //clicked column is already sorted. If asc then change to desc. If desc, then disable
            //sorting on this column
            if(hdr.sort_direction()=="asc"){
                hdr.sort_direction("desc")
            }
            else{
                //disable sorting for this column
                hdr.sort_direction("")
                hdr.sorted(false)
            }
        }
        else{
            //disable sorting on all other columns and enable asc sorting for this column
            self.headers().forEach(function(elem){
                elem.sorted(false)
                elem.sort_direction("")
            })
            hdr.sort_direction("asc")
            hdr.sorted(true)
        }
        //refresh data here...
        self.refresh_data()
    }

    // refresh data with sorting and paging
    self.refresh_data = function(){
        if(self.custom_refresh!=null){
            return self.custom_refresh()
        }
        self.isLoading(true)
        var url = self.url()+"?page="+self.page()+"&page-size="+self.page_size()
        //find which column we are sorting on and sort direction
        for(var i=0; i<self.headers().length; i++){
            var h=self.headers()[i]
            if(h.sorted()){
                url+= "&sort="+h.name()+"|"+(h.sort_direction()=="asc"?"asc":"desc")
                break
            }
        }
        json_get(url, function(data){
            self.isLoading(false);
        })
    }

}

